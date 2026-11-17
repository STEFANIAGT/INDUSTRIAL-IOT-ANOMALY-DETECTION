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


def headers(originator, resource_type=None):
    h = {
        "X-M2M-Origin": originator,
        "X-M2M-RI": f"req-{uuid.uuid4().hex[:8]}",
        "X-M2M-RVI": "4",
        "Accept": "application/json",
    }
    if resource_type is not None:
        h["Content-Type"] = f"application/json;ty={resource_type}"
    else:
        h["Content-Type"] = "application/json"
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
    # Reproducible tuning run.
    random.seed(20261115)
    np.random.seed(20261115)

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

        results.append(
            {
                "nu": nu,
                "fpr": fpr,
                "detection": detection,
                "model": model,
            }
        )

        print(
            f"nu={nu:0.3f} | "
            f"normal false-positive rate={fpr:6.2%} | "
            f"anomaly detection={detection:6.2%}"
        )

    # Prefer models with >=95% anomaly detection. Among those, minimize false
    # positives first, then maximize anomaly detection.
    acceptable = [r for r in results if r["detection"] >= 0.95]

    if acceptable:
        best = min(
            acceptable,
            key=lambda r: (r["fpr"], -r["detection"], r["nu"]),
        )
    else:
        # Fallback: maximize a score that strongly penalizes false positives.
        best = max(
            results,
            key=lambda r: (r["detection"] - 2.0 * r["fpr"], r["detection"]),
        )

    return best


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def save_and_publish(best):
    model = best["model"]
    nu = best["nu"]

    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_FILE, compress=3)

    raw = MODEL_FILE.read_bytes()
    digest = sha256_bytes(raw)
    payload = base64.b64encode(raw).decode("ascii")

    print()
    print(f"[SELECTED] nu={nu}")
    print(f"[SELECTED] false-positive rate={best['fpr']:.2%}")
    print(f"[SELECTED] anomaly detection={best['detection']:.2%}")
    print(f"[OK] Saved tuned model: {MODEL_FILE.name}")
    print(f"[INFO] SHA-256: {digest}")

    v2_url = f"{IN_BASE}/ModelManagerAE/modelRepo/anomalyModel/v2"

    existing = requests.get(
        v2_url,
        headers=headers(MODEL_MANAGER),
        timeout=10,
    )

    if existing.status_code == 200:
        r = requests.delete(
            v2_url,
            headers=headers(MODEL_MANAGER),
            timeout=10,
        )
        if r.status_code not in (200, 202, 204):
            print(f"[ERROR] Cannot replace old v2: HTTP {r.status_code}")
            print(r.text)
            raise SystemExit(1)

        print("[OK] Removed previous cloud v2.")

    body = {
        "m2m:cin": {
            "rn": "v2",
            "con": {
                "modelName": "motor-anomaly-detector",
                "version": "v2",
                "status": "available",
                "algorithm": "OneClassSVM",
                "nu": nu,
                "validationFalsePositiveRate": round(best["fpr"], 6),
                "validationAnomalyDetectionRate": round(best["detection"], 6),
                "file": MODEL_FILE.name,
                "sha256": digest,
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "target": "MN-CSE /id-mn",
                "encoding": "base64",
                "payloadBase64": payload,
            }
        }
    }

    r = requests.post(
        f"{IN_BASE}/ModelManagerAE/modelRepo/anomalyModel",
        headers=headers(MODEL_MANAGER, 4),
        json=body,
        timeout=30,
    )

    if r.status_code not in (200, 201):
        print(f"[ERROR] Cannot publish tuned v2: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    print("[OK] Published tuned v2 to IN-CSE modelRepo.")


def main():
    print("Tuning model v2 to reduce false positives...")
    print()

    if not TRAINING_FILE.exists():
        print(f"[ERROR] Training file not found: {TRAINING_FILE}")
        raise SystemExit(1)

    df = pd.read_csv(TRAINING_FILE)
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        print(f"[ERROR] Missing training columns: {missing}")
        raise SystemExit(1)

    X_train = df[FEATURES]
    X_normal, X_anomaly = build_validation_sets()

    best = evaluate_candidates(X_train, X_normal, X_anomaly)
    save_and_publish(best)

    print()
    print("DONE. Tuned v2 is available in the cloud.")
    print("Next: run deploy_model_v2_to_edge.py again.")


if __name__ == "__main__":
    main()
