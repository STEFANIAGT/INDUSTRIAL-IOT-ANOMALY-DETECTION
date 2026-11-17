import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

IN_BASE = "http://127.0.0.1:8081/cse-in"
MODEL_MANAGER = "CModelManagerAE"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_FILE = PROJECT_ROOT / "models" / "anomaly_model.joblib"


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


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get(path, originator="CAdmin"):
    return requests.get(
        f"{IN_BASE}/{path}" if path else IN_BASE,
        headers=headers(originator),
        timeout=5,
    )


def create(url, originator, ty, body, label):
    r = requests.post(
        url,
        headers=headers(originator, ty),
        json=body,
        timeout=5,
    )

    if r.status_code in (200, 201):
        print(f"[OK] Created: {label}")
        try:
            return r.json()
        except ValueError:
            return None

    if r.status_code == 409:
        print(f"[SKIP] Already exists: {label}")
        return None

    print(f"[ERROR] {label}: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def main():
    print("Setting up cloud model repository on IN-CSE...")
    print()

    r = get("")
    if r.status_code != 200:
        print(f"[ERROR] IN-CSE not reachable: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    print("[OK] IN-CSE reachable on port 8081")

    ae_result = create(
        IN_BASE,
        MODEL_MANAGER,
        2,
        {
            "m2m:ae": {
                "rn": "ModelManagerAE",
                "api": "Norg.unimore.elektra.modelmanager",
                "rr": True,
                "srv": ["4"],
            }
        },
        "ModelManagerAE",
    )

    originator = MODEL_MANAGER
    if isinstance(ae_result, dict):
        originator = ae_result.get("m2m:ae", {}).get("aei", MODEL_MANAGER)

    create(
        f"{IN_BASE}/ModelManagerAE",
        originator,
        3,
        {"m2m:cnt": {"rn": "modelRepo", "mni": 20}},
        "modelRepo",
    )

    create(
        f"{IN_BASE}/ModelManagerAE/modelRepo",
        originator,
        3,
        {"m2m:cnt": {"rn": "anomalyModel", "mni": 20}},
        "anomalyModel",
    )

    if not MODEL_FILE.exists():
        print(f"[ERROR] Local model file not found: {MODEL_FILE}")
        raise SystemExit(1)

    metadata = {
        "modelName": "motor-anomaly-detector",
        "version": "v1",
        "algorithm": "OneClassSVM",
        "file": MODEL_FILE.name,
        "sha256": sha256_file(MODEL_FILE),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "target": "MN-CSE /id-mn",
        "deploymentStatus": "available",
    }

    create(
        f"{IN_BASE}/ModelManagerAE/modelRepo/anomalyModel",
        originator,
        4,
        {"m2m:cin": {"rn": "v1", "con": metadata}},
        "model version v1",
    )

    print()
    print("DONE. Cloud model repository is ready.")
    print()
    print("Expected IN-CSE tree:")
    print("cse-in")
    print("`-- ModelManagerAE")
    print("    `-- modelRepo")
    print("        `-- anomalyModel")
    print("            `-- v1")


if __name__ == "__main__":
    main()
