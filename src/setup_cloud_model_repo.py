import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

IN_BASE = "http://127.0.0.1:8081/cse-in"

ADMIN = "CAdmin"
MODEL_MANAGER_REGISTRATION_ORIGINATOR = "CModelManagerAE"

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


def get(path, originator=ADMIN):
    url = IN_BASE if not path else f"{IN_BASE}/{path}"
    return requests.get(url, headers=headers(originator), timeout=5)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model_manager_ae():
    r = get("ModelManagerAE", ADMIN)

    if r.status_code == 200:
        ae = r.json().get("m2m:ae", {})
        aei = ae.get("aei")
        if not aei:
            raise RuntimeError("ModelManagerAE exists but no AE-ID (aei) was returned.")
        print(f"[SKIP] ModelManagerAE already exists (aei={aei})")
        return aei

    if r.status_code != 404:
        raise RuntimeError(
            f"Cannot check ModelManagerAE: HTTP {r.status_code} - {r.text}"
        )

    body = {
        "m2m:ae": {
            "rn": "ModelManagerAE",
            "api": "Norg.unimore.elektra.modelmanager",
            "rr": True,
            "srv": ["4"],
        }
    }

    r = requests.post(
        IN_BASE,
        headers=headers(MODEL_MANAGER_REGISTRATION_ORIGINATOR, 2),
        json=body,
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create ModelManagerAE: HTTP {r.status_code} - {r.text}"
        )

    ae = r.json().get("m2m:ae", {})
    aei = ae.get("aei")
    if not aei:
        raise RuntimeError("ModelManagerAE created but no AE-ID was returned.")

    print(f"[OK] Created ModelManagerAE (aei={aei})")
    return aei


def ensure_container(path, rn, originator, mni=20):
    r = get(path, ADMIN)

    if r.status_code == 200:
        if "m2m:cnt" not in r.json():
            raise RuntimeError(f"{path} exists but is not a Container.")
        print(f"[SKIP] {rn} already exists")
        return

    if r.status_code != 404:
        raise RuntimeError(
            f"Cannot check {path}: HTTP {r.status_code} - {r.text}"
        )

    parent = path.rsplit("/", 1)[0]
    body = {"m2m:cnt": {"rn": rn, "mni": mni}}

    r = requests.post(
        f"{IN_BASE}/{parent}",
        headers=headers(originator, 3),
        json=body,
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create {rn}: HTTP {r.status_code} - {r.text}"
        )

    print(f"[OK] Created {rn}")


def desired_v1_metadata():
    if not MODEL_FILE.exists():
        raise RuntimeError(f"Local v1 model file not found: {MODEL_FILE}")

    return {
        "modelName": "motor-anomaly-detector",
        "version": "v1",
        "algorithm": "OneClassSVM",
        "file": MODEL_FILE.name,
        "sha256": sha256_file(MODEL_FILE),
        "target": "MN-CSE /id-mn",
        "deploymentStatus": "available",
    }


def ensure_v1(originator):
    desired = desired_v1_metadata()

    r = get(
        "ModelManagerAE/modelRepo/anomalyModel/v1",
        ADMIN,
    )

    if r.status_code == 200:
        cin = r.json().get("m2m:cin", {})
        con = cin.get("con", {})

        if not isinstance(con, dict):
            raise RuntimeError("Cloud model v1 exists but metadata is not a JSON object.")

        if con.get("version") != "v1":
            raise RuntimeError("Resource named v1 exists but metadata version is not v1.")

        existing_hash = con.get("sha256")
        if existing_hash != desired["sha256"]:
            raise RuntimeError(
                "Cloud v1 already exists but its SHA-256 does not match "
                "models/anomaly_model.joblib. "
                "Do not overwrite an existing model version automatically."
            )

        print("[SKIP] Cloud model v1 already exists and checksum matches")
        return

    if r.status_code != 404:
        raise RuntimeError(
            f"Cannot check cloud v1: HTTP {r.status_code} - {r.text}"
        )

    metadata = {
        **desired,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    r = requests.post(
        f"{IN_BASE}/ModelManagerAE/modelRepo/anomalyModel",
        headers=headers(originator, 4),
        json={
            "m2m:cin": {
                "rn": "v1",
                "con": metadata,
            }
        },
        timeout=10,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create cloud model v1: HTTP {r.status_code} - {r.text}"
        )

    print("[OK] Created cloud model version v1")


def main():
    print("ELEKTRA - idempotent cloud model repository setup")
    print("-" * 60)

    try:
        r = get("", ADMIN)
        if r.status_code != 200:
            raise RuntimeError(
                f"IN-CSE is not reachable: HTTP {r.status_code} - {r.text}"
            )

        print("[OK] IN-CSE reachable on port 8081")

        model_manager_aei = ensure_model_manager_ae()

        ensure_container(
            "ModelManagerAE/modelRepo",
            "modelRepo",
            model_manager_aei,
        )

        ensure_container(
            "ModelManagerAE/modelRepo/anomalyModel",
            "anomalyModel",
            model_manager_aei,
        )

        ensure_v1(model_manager_aei)

    except requests.RequestException as exc:
        print(f"[ERROR] Cannot contact IN-CSE: {exc}")
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print()
    print("[DONE] Cloud model repository is ready.")
    print("The script can be safely executed again.")


if __name__ == "__main__":
    main()

