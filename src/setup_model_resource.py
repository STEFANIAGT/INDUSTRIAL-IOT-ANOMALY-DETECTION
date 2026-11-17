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


def get(path, originator=ADMIN):
    return requests.get(
        f"{BASE_URL}/{path}",
        headers=headers(originator),
        timeout=5,
    )


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model_container():
    r = get("model", ADMIN)

    if r.status_code == 200:
        if "m2m:cnt" not in r.json():
            raise RuntimeError("model exists but is not a Container.")
        print("[SKIP] model container already exists")
        return

    if r.status_code != 404:
        raise RuntimeError(
            f"Cannot check model container: HTTP {r.status_code} - {r.text}"
        )

    body = {"m2m:cnt": {"rn": "model", "mni": 20}}

    r = requests.post(
        BASE_URL,
        headers=headers(ADMIN, 3),
        json=body,
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create model container: HTTP {r.status_code} - {r.text}"
        )

    print("[OK] Created model container")


def ensure_model_acp():
    privileges = [
        {"acor": [ANOMALY_AE], "acop": 2},
        {"acor": [ADMIN], "acop": 63},
    ]
    self_privileges = [
        {"acor": [ADMIN], "acop": 63},
    ]

    body = {
        "m2m:acp": {
            "pv": {"acr": privileges},
            "pvs": {"acr": self_privileges},
        }
    }

    r = get("modelACP", ADMIN)

    if r.status_code == 200:
        r = requests.put(
            f"{BASE_URL}/modelACP",
            headers=headers(ADMIN),
            json=body,
            timeout=5,
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"Cannot update modelACP: HTTP {r.status_code} - {r.text}"
            )
        print("[OK] Updated modelACP")
        return r.json()["m2m:acp"]["ri"]

    if r.status_code != 404:
        raise RuntimeError(
            f"Cannot check modelACP: HTTP {r.status_code} - {r.text}"
        )

    create_body = {
        "m2m:acp": {
            "rn": "modelACP",
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

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create modelACP: HTTP {r.status_code} - {r.text}"
        )

    print("[OK] Created modelACP")
    return r.json()["m2m:acp"]["ri"]


def ensure_model_acp_assignment(acp_ri):
    r = get("model", ADMIN)
    if r.status_code != 200:
        raise RuntimeError(
            f"Cannot retrieve model container: HTTP {r.status_code} - {r.text}"
        )

    current = r.json()["m2m:cnt"].get("acpi", [])
    if current == [acp_ri]:
        print("[SKIP] modelACP already assigned to model container")
        return

    body = {"m2m:cnt": {"acpi": [acp_ri]}}

    r = requests.put(
        f"{BASE_URL}/model",
        headers=headers(ADMIN),
        json=body,
        timeout=5,
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"Cannot assign modelACP: HTTP {r.status_code} - {r.text}"
        )

    print("[OK] modelACP assigned to model container")


def desired_metadata():
    if not MODEL_FILE.exists():
        raise RuntimeError(f"Model file not found: {MODEL_FILE}")

    return {
        "modelName": "motor-anomaly-detector",
        "version": "v1",
        "status": "active",
        "algorithm": "OneClassSVM",
        "file": MODEL_FILE.name,
        "sha256": sha256_file(MODEL_FILE),
    }


def ensure_initial_active_model():
    desired = desired_metadata()

    r = get("model/la", ADMIN)

    if r.status_code == 200:
        con = r.json().get("m2m:cin", {}).get("con", {})
        if isinstance(con, dict):
            same = all(con.get(k) == v for k, v in desired.items())
            if same:
                print("[SKIP] Active model metadata already matches v1")
                return

            # If a newer active model is already deployed, never overwrite it.
            if con.get("status") == "active" and con.get("version") != "v1":
                print(
                    f"[SKIP] A different active model is already configured "
                    f"(version={con.get('version')})."
                )
                return

    elif r.status_code != 404:
        raise RuntimeError(
            f"Cannot check active model metadata: HTTP {r.status_code} - {r.text}"
        )

    metadata = {
        **desired,
        "deployedAt": datetime.now(timezone.utc).isoformat(),
    }

    r = requests.post(
        f"{BASE_URL}/model",
        headers=headers(ADMIN, 4),
        json={"m2m:cin": {"con": metadata}},
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot publish model metadata: HTTP {r.status_code} - {r.text}"
        )

    print("[OK] Published initial active model metadata: v1")


def verify():
    r = get("model/la", ANOMALY_AE)

    if r.status_code != 200:
        raise RuntimeError(
            f"AnomalyDetectionAE cannot read model metadata: "
            f"HTTP {r.status_code} - {r.text}"
        )

    con = r.json().get("m2m:cin", {}).get("con", {})
    print(
        "[OK] AnomalyDetectionAE can read active model metadata: "
        f"version={con.get('version')} | status={con.get('status')} | "
        f"file={con.get('file')}"
    )


def main():
    print("ELEKTRA - idempotent active model setup")
    print("-" * 60)

    try:
        r = requests.get(
            BASE_URL,
            headers=headers(ADMIN),
            timeout=5,
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"ACME MN-CSE is not reachable: HTTP {r.status_code} - {r.text}"
            )

        print("[OK] ACME MN-CSE reachable")

        ensure_model_container()
        acp_ri = ensure_model_acp()
        ensure_model_acp_assignment(acp_ri)
        ensure_initial_active_model()
        verify()

    except requests.RequestException as exc:
        print(f"[ERROR] Cannot contact ACME MN-CSE: {exc}")
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print()
    print("[DONE] Active model setup is ready.")
    print("The script can be safely executed again.")


if __name__ == "__main__":
    main()
