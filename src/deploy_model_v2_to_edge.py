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
        "Content-Type": "application/json",
    }
    if resource_type is not None:
        h["Content-Type"] = f"application/json;ty={resource_type}"
    return h


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retrieve_v2_through_mcc():
    url = MN_HTTP + REMOTE_V2
    r = requests.get(url, headers=headers(ADMIN), timeout=15)

    if r.status_code != 200:
        raise RuntimeError(
            f"Mcc retrieval failed: HTTP {r.status_code} - {r.text}"
        )

    con = r.json().get("m2m:cin", {}).get("con")

    if not isinstance(con, dict):
        raise RuntimeError("Remote v2 content is not valid JSON metadata.")

    if con.get("version") != "v2":
        raise RuntimeError("Remote resource v2 does not contain version=v2.")

    print("[OK] Retrieved model v2 from IN-CSE through MN-CSE / Mcc.")
    return con


def decode_and_verify(con):
    payload = con.get("payloadBase64")
    expected_hash = con.get("sha256")
    filename = Path(con.get("file", "anomaly_model_v2.joblib")).name

    if not payload or not expected_hash:
        raise RuntimeError("v2 metadata is missing payloadBase64 or sha256.")

    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise RuntimeError(f"Invalid Base64 model payload: {exc}") from exc

    actual_hash = sha256_bytes(raw)

    if actual_hash != expected_hash:
        raise RuntimeError(
            "SHA-256 verification FAILED. "
            f"Expected={expected_hash}, actual={actual_hash}"
        )

    print("[OK] SHA-256 verified.")
    return raw, filename, actual_hash


def ensure_local_model(raw, filename, digest):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / filename

    if target.exists() and sha256_file(target) == digest:
        print(f"[SKIP] Local edge model already matches: models/{filename}")
        return target

    target.write_bytes(raw)

    if sha256_file(target) != digest:
        raise RuntimeError("Saved local model failed SHA-256 verification.")

    print(f"[OK] Saved edge model file: models/{filename}")
    return target


def get_active_model_metadata():
    r = requests.get(
        f"{MN_CSE}/model/la",
        headers=headers(ADMIN),
        timeout=5,
    )

    if r.status_code == 404:
        return None

    if r.status_code != 200:
        raise RuntimeError(
            f"Cannot retrieve active model metadata: "
            f"HTTP {r.status_code} - {r.text}"
        )

    con = r.json().get("m2m:cin", {}).get("con")
    return con if isinstance(con, dict) else None


def ensure_active_v2(con, target, digest):
    current = get_active_model_metadata()

    if current:
        if (
            current.get("version") == "v2"
            and current.get("status") == "active"
            and current.get("file") == target.name
            and current.get("sha256") == digest
        ):
            print("[SKIP] MN-CSE already has this exact v2 as ACTIVE.")
            return

    active_metadata = {
        "modelName": con.get("modelName", "motor-anomaly-detector"),
        "version": "v2",
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
        raise RuntimeError(
            f"Could not activate v2 on MN-CSE: "
            f"HTTP {r.status_code} - {r.text}"
        )

    print("[OK] MN-CSE model resource updated: v2 is ACTIVE.")


def verify_active():
    current = get_active_model_metadata()

    if not current:
        raise RuntimeError("No active model metadata found after deployment.")

    print()
    print("[VERIFY] Active edge model:")
    print(f"         version={current.get('version')}")
    print(f"         status={current.get('status')}")
    print(f"         file={current.get('file')}")
    print(f"         source={current.get('source')}")


def main():
    print("ELEKTRA - idempotent cloud-to-edge model deployment")
    print("-" * 60)

    try:
        con = retrieve_v2_through_mcc()
        raw, filename, digest = decode_and_verify(con)
        target = ensure_local_model(raw, filename, digest)
        ensure_active_v2(con, target, digest)
        verify_active()

    except requests.RequestException as exc:
        print(f"[ERROR] Network error: {exc}")
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print()
    print("[DONE] Cloud -> edge model deployment is ready.")
    print("The script can be safely executed again.")


if __name__ == "__main__":
    main()

