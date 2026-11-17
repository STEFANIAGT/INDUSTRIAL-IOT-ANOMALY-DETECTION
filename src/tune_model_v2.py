import base64
import hashlib
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from sensor_simulator import normal_reading, anomalous_reading

IN_BASE = "http://127.0.0.1:8081/cse-in"
MODEL_MANAGER = "CModelManagerAE"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAINING_FILE = PROJECT_ROOT / "data" / "training_normal.csv"
MODEL_FILE = PROJECT_ROOT / "models" / "anomaly_model_v2.joblib"

FEATURES = ["temperature", "vibration", "current"]
CANDIDATE_NU = [0.003, 0.005, 0.008, 0.010, 0.012, 0.015]

NORMAL_VALIDATION = 800
ANOMALY_VALIDATION = 250

# Fixed seed: repeated executions use the same synthetic validation set.
RANDOM_SEED = 20261115


def headers(originator, resource_type=None):
    h = {
        "X-M2M-Origin": originator,
        "X-M2M-RI": f"req-{uuid.uuid4().hex[:8]}",
        "X-M2M-RVI": "4",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if resource_type is not None:
        h["Content-Type"] = f"application/json;ty={resource_type}"
    return h


def make_model(nu):
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("ocsvm", OneClassSVM(kernel="rbf", gamma="scale", nu=nu)),
        ]
    )


def reading_row(reading):
    d = reading.as_dict()
    return [d["temperature"], d["vibration"], d["current"]]


def build_validation_sets():
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    normal = pd.DataFrame(
        [reading_row(normal_reading()) for _ in range(NORMAL_VALIDATION)],
        columns=FEATURES,
    )

    anomalous = pd.DataFrame(
        [reading_row(anomalous_reading()) for _ in range(ANOMALY_VALIDATION)],
        columns=FEATURES,
    )

    return normal, anomalous


def evaluate_candidates(X_train, X_normal, X_anomaly):
    results = []

    print("Evaluating candidate nu values...")
    print("-" * 76)

    for nu in CANDIDATE_NU:
        model = make_model(nu)
        model.fit(X_train)

        normal_pred = model.predict(X_normal)
        anomaly_pred = model.predict(X_anomaly)

        false_positives = int((normal_pred == -1).sum())
        true_anomalies = int((anomaly_pred == -1).sum())

        fpr = false_positives / len(X_normal)
        detection = true_anomalies / len(X_anomaly)

        result = {
            "nu": nu,
            "fpr": fpr,
            "detection": detection,
            "model": model,
        }
        results.append(result)

        print(
            f"nu={nu:0.3f} | "
            f"normal false-positive rate={fpr:6.2%} | "
            f"anomaly detection={detection:6.2%}"
        )

    acceptable = [r for r in results if r["detection"] >= 0.95]

    if acceptable:
        return min(
            acceptable,
            key=lambda r: (r["fpr"], -r["detection"], r["nu"]),
        )

    return max(
        results,
        key=lambda r: (r["detection"] - 2.0 * r["fpr"], r["detection"]),
    )


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def build_model_artifact(best):
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Dump to the official v2 path.
    joblib.dump(best["model"], MODEL_FILE, compress=3)

    raw = MODEL_FILE.read_bytes()
    digest = sha256_bytes(raw)
    payload = base64.b64encode(raw).decode("ascii")

    print()
    print(f"[SELECTED] nu={best['nu']}")
    print(f"[SELECTED] false-positive rate={best['fpr']:.2%}")
    print(f"[SELECTED] anomaly detection={best['detection']:.2%}")
    print(f"[OK] Local tuned model ready: {MODEL_FILE.name}")
    print(f"[INFO] SHA-256: {digest}")

    return raw, digest, payload


def get_existing_cloud_v2():
    r = requests.get(
        f"{IN_BASE}/ModelManagerAE/modelRepo/anomalyModel/v2",
        headers=headers(MODEL_MANAGER),
        timeout=10,
    )

    if r.status_code == 404:
        return None

    if r.status_code != 200:
        raise RuntimeError(
            f"Cannot check cloud v2: HTTP {r.status_code} - {r.text}"
        )

    con = r.json().get("m2m:cin", {}).get("con")
    if not isinstance(con, dict):
        raise RuntimeError("Existing cloud v2 metadata is invalid.")

    return con


def publish_or_skip(best, digest, payload):
    existing = get_existing_cloud_v2()

    if existing and existing.get("sha256") == digest:
        print("[SKIP] Cloud v2 already contains the same model checksum")
        print(
            f"[OK] Existing cloud v2: nu={existing.get('nu')} | "
            f"FPR={existing.get('validationFalsePositiveRate')} | "
            f"detection={existing.get('validationAnomalyDetectionRate')}"
        )
        return

    if existing:
        r = requests.delete(
            f"{IN_BASE}/ModelManagerAE/modelRepo/anomalyModel/v2",
            headers=headers(MODEL_MANAGER),
            timeout=10,
        )

        if r.status_code not in (200, 202, 204):
            raise RuntimeError(
                f"Cannot replace old cloud v2: HTTP {r.status_code} - {r.text}"
            )

        print("[OK] Removed previous cloud v2 because the tuned model changed")

    metadata = {
        "modelName": "motor-anomaly-detector",
        "version": "v2",
        "status": "available",
        "algorithm": "OneClassSVM",
        "nu": best["nu"],
        "validationFalsePositiveRate": round(best["fpr"], 6),
        "validationAnomalyDetectionRate": round(best["detection"], 6),
        "file": MODEL_FILE.name,
        "sha256": digest,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "target": "MN-CSE /id-mn",
        "encoding": "base64",
        "payloadBase64": payload,
    }

    r = requests.post(
        f"{IN_BASE}/ModelManagerAE/modelRepo/anomalyModel",
        headers=headers(MODEL_MANAGER, 4),
        json={"m2m:cin": {"rn": "v2", "con": metadata}},
        timeout=30,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot publish tuned v2: HTTP {r.status_code} - {r.text}"
        )

    print("[OK] Published tuned v2 to IN-CSE modelRepo")


def main():
    print("ELEKTRA - idempotent model v2 tuning")
    print("-" * 60)

    try:
        if not TRAINING_FILE.exists():
            raise RuntimeError(f"Training file not found: {TRAINING_FILE}")

        df = pd.read_csv(TRAINING_FILE)
        missing = [c for c in FEATURES if c not in df.columns]
        if missing:
            raise RuntimeError(f"Missing training columns: {missing}")

        # Make sure the cloud repository exists before tuning/publishing.
        r = requests.get(
            f"{IN_BASE}/ModelManagerAE/modelRepo/anomalyModel",
            headers=headers(MODEL_MANAGER),
            timeout=5,
        )
        if r.status_code != 200:
            raise RuntimeError(
                "Cloud anomalyModel repository is not available. "
                "Run setup_cloud_model_repo.py and setup_cloud_repo_acp.py first."
            )

        X_train = df[FEATURES]
        X_normal, X_anomaly = build_validation_sets()

        best = evaluate_candidates(X_train, X_normal, X_anomaly)
        _, digest, payload = build_model_artifact(best)
        publish_or_skip(best, digest, payload)

    except requests.RequestException as exc:
        print(f"[ERROR] Cannot contact IN-CSE: {exc}")
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print()
    print("[DONE] Tuned v2 is ready in the cloud.")
    print("The script can be safely executed again.")
    print("Next: run deploy_model_v2_to_edge.py.")


if __name__ == "__main__":
    main()

