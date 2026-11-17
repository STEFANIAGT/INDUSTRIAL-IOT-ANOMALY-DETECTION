import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8080/cse-mn"

ADMIN = "CAdmin"
ANOMALY_AE = "CAnomalyDetectionAE"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_FILE = PROJECT_ROOT / "models" / "anomaly_model.joblib"


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


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get(path, originator=ADMIN):
    return requests.get(
        f"{BASE_URL}/{path}",
        headers=headers(originator),
        timeout=5,
    )


def create_model_container():
    r = get("model", ADMIN)

    if r.status_code == 200:
        print("[SKIP] model container already exists.")
        return

    if r.status_code != 404:
        print(f"[ERROR] Cannot check model container: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    body = {
        "m2m:cnt": {
            "rn": "model",
            "mni": 20
        }
    }

    r = requests.post(
        BASE_URL,
        headers=headers(ADMIN, 3),
        json=body,
        timeout=5,
    )

    if r.status_code in (200, 201):
        print("[OK] Created model container.")
        return

    print(f"[ERROR] Cannot create model container: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def create_or_update_model_acp():
    rn = "modelACP"

    privileges = [
        {"acor": [ANOMALY_AE], "acop": 2},
        {"acor": [ADMIN], "acop": 63},
    ]

    self_privileges = [
        {"acor": [ADMIN], "acop": 63},
    ]

    existing = get(rn, ADMIN)

    body = {
        "m2m:acp": {
            "pv": {"acr": privileges},
            "pvs": {"acr": self_privileges},
        }
    }

    if existing.status_code == 200:
        r = requests.put(
            f"{BASE_URL}/{rn}",
            headers=headers(ADMIN),
            json=body,
            timeout=5,
        )

        if r.status_code == 200:
            print("[OK] Updated modelACP.")
            return r.json()["m2m:acp"]["ri"]

        print(f"[ERROR] Cannot update modelACP: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    if existing.status_code != 404:
        print(f"[ERROR] Cannot check modelACP: HTTP {existing.status_code}")
        print(existing.text)
        raise SystemExit(1)

    create_body = {
        "m2m:acp": {
            "rn": rn,
            "pv": {"acr": privileges},
            "pvs": {"acr": self_privileges},
        }
    }

    r = requests.post(
        BASE_URL,
        headers=headers(ADMIN, 1),
        json=create_body,
        timeout=5,
    )

    if r.status_code in (200, 201):
        print("[OK] Created modelACP.")
        return r.json()["m2m:acp"]["ri"]

    print(f"[ERROR] Cannot create modelACP: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def assign_model_acp(acp_ri):
    body = {
        "m2m:cnt": {
            "acpi": [acp_ri]
        }
    }

    r = requests.put(
        f"{BASE_URL}/model",
        headers=headers(ADMIN),
        json=body,
        timeout=5,
    )

    if r.status_code == 200:
        print("[OK] modelACP assigned to model container.")
        return

    print(f"[ERROR] Cannot assign modelACP: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def publish_active_model_metadata():
    if not MODEL_FILE.exists():
        print(f"[ERROR] Model file not found: {MODEL_FILE}")
        raise SystemExit(1)

    metadata = {
        "modelName": "motor-anomaly-detector",
        "version": "v1",
        "status": "active",
        "algorithm": "OneClassSVM",
        "file": MODEL_FILE.name,
        "sha256": sha256_file(MODEL_FILE),
        "deployedAt": datetime.now(timezone.utc).isoformat(),
    }

    body = {
        "m2m:cin": {
            "con": metadata
        }
    }

    r = requests.post(
        f"{BASE_URL}/model",
        headers=headers(ADMIN, 4),
        json=body,
        timeout=5,
    )

    if r.status_code in (200, 201):
        print("[OK] Published active model metadata: v1")
        return

    print(f"[ERROR] Cannot publish model metadata: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def verify():
    print()
    print("Checking model permissions...")

    r = get("model/la", ANOMALY_AE)
    if r.status_code == 200:
        try:
            con = r.json()["m2m:cin"]["con"]
            print("[OK] AnomalyDetectionAE can read active model metadata.")
            print(f"     version={con.get('version')} | status={con.get('status')} | file={con.get('file')}")
        except Exception:
            print("[OK] AnomalyDetectionAE can retrieve model metadata.")
    else:
        print(f"[ERROR] AnomalyDetectionAE cannot read model metadata: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)


def main():
    print("Setting up active AI model resource in the MN-CSE...")
    print()

    create_model_container()
    acp_ri = create_or_update_model_acp()
    assign_model_acp(acp_ri)
    publish_active_model_metadata()
    verify()

    print()
    print("DONE. Active model resource is available in oneM2M.")
    print()
    print("Expected tree:")
    print("cse-mn")
    print("|-- model")
    print("|   `-- <contentInstance> -> version v1, status active")
    print("`-- modelACP")


if __name__ == "__main__":
    main()
