import base64
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

MN_HTTP = "http://127.0.0.1:8080"
MN_CSE = "http://127.0.0.1:8080/cse-mn"
REMOTE_V2 = "/~/id-in/cse-in/ModelManagerAE/modelRepo/anomalyModel/v2"

ADMIN = "CAdmin"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"


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


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def retrieve_v2_through_mcc():
    url = MN_HTTP + REMOTE_V2
    r = requests.get(url, headers=headers(ADMIN), timeout=15)

    if r.status_code != 200:
        print(f"[ERROR] Mcc retrieval failed: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    data = r.json()
    con = data.get("m2m:cin", {}).get("con")

    if not isinstance(con, dict):
        print("[ERROR] Remote v2 content is not valid JSON metadata.")
        raise SystemExit(1)

    print("[OK] Retrieved model v2 from IN-CSE through MN-CSE / Mcc.")
    return con


def decode_and_save(con):
    payload = con.get("payloadBase64")
    expected_hash = con.get("sha256")
    filename = Path(con.get("file", "anomaly_model_v2.joblib")).name

    if not payload or not expected_hash:
        print("[ERROR] v2 metadata is missing payloadBase64 or sha256.")
        raise SystemExit(1)

    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as exc:
        print(f"[ERROR] Invalid Base64 model payload: {exc}")
        raise SystemExit(1)

    actual_hash = sha256_bytes(raw)

    if actual_hash != expected_hash:
        print("[ERROR] SHA-256 verification FAILED.")
        print(f"Expected: {expected_hash}")
        print(f"Actual:   {actual_hash}")
        raise SystemExit(1)

    print("[OK] SHA-256 verified.")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / filename
    target.write_bytes(raw)

    print(f"[OK] Saved edge model file: models/{filename}")
    return target, actual_hash


def activate_on_mn(con, target, digest):
    active_metadata = {
        "modelName": con.get("modelName", "motor-anomaly-detector"),
        "version": con.get("version", "v2"),
        "status": "active",
        "algorithm": con.get("algorithm", "OneClassSVM"),
        "file": target.name,
        "sha256": digest,
        "source": "IN-CSE /id-in via Mcc",
        "sourceResource": "ModelManagerAE/modelRepo/anomalyModel/v2",
        "deployedAt": datetime.now(timezone.utc).isoformat(),
    }

    r = requests.post(
        f"{MN_CSE}/model",
        headers=headers(ADMIN, 4),
        json={"m2m:cin": {"con": active_metadata}},
        timeout=10,
    )

    if r.status_code not in (200, 201):
        print(f"[ERROR] Could not activate v2 on MN-CSE: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    print("[OK] MN-CSE model resource updated: v2 is ACTIVE.")


def verify_active():
    r = requests.get(
        f"{MN_CSE}/model/la",
        headers=headers(ADMIN),
        timeout=5,
    )

    if r.status_code != 200:
        print(f"[ERROR] Cannot verify active model: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    con = r.json().get("m2m:cin", {}).get("con", {})
    print()
    print("[VERIFY] Active edge model:")
    print(f"         version={con.get('version')}")
    print(f"         status={con.get('status')}")
    print(f"         file={con.get('file')}")
    print(f"         source={con.get('source')}")


def main():
    print("Deploying cloud model v2 to the edge through oneM2M Mcc...")
    print()

    con = retrieve_v2_through_mcc()
    target, digest = decode_and_save(con)
    activate_on_mn(con, target, digest)
    verify_active()

    print()
    print("DONE. Cloud -> edge model deployment completed successfully.")


if __name__ == "__main__":
    main()
