import socket
import uuid
import requests

BASE_URL = "http://127.0.0.1:8080/cse-mn"
ORIGINATOR = "CSensorAE"

SUB_PARENT = "SensorAE/machine01/current"
SUB_NAME = "newReadingSubscription"
SUB_PATH = f"{SUB_PARENT}/{SUB_NAME}"

NOTIFICATION_HOST = "127.0.0.1"
NOTIFICATION_PORT = 9999
NOTIFICATION_URL = f"http://{NOTIFICATION_HOST}:{NOTIFICATION_PORT}/notify"


def headers(resource_type=None):
    h = {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": f"req-{uuid.uuid4().hex[:8]}",
        "X-M2M-RVI": "4",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if resource_type is not None:
        h["Content-Type"] = f"application/json;ty={resource_type}"
    return h


def get_resource(path):
    return requests.get(
        f"{BASE_URL}/{path}",
        headers=headers(),
        timeout=5,
    )


def notification_server_is_running():
    try:
        with socket.create_connection(
            (NOTIFICATION_HOST, NOTIFICATION_PORT),
            timeout=2,
        ):
            return True
    except OSError:
        return False


def desired_subscription():
    return {
        "nu": [NOTIFICATION_URL],
        "enc": {"net": [3]},
        "nct": 1,
    }


def subscription_matches(current):
    desired = desired_subscription()

    current_nu = current.get("nu", [])
    current_enc = current.get("enc", {})
    current_net = current_enc.get("net", [])
    current_nct = current.get("nct")

    return (
        current_nu == desired["nu"]
        and current_net == desired["enc"]["net"]
        and current_nct == desired["nct"]
    )


def ensure_parent_exists():
    r = get_resource(SUB_PARENT)

    if r.status_code != 200:
        raise RuntimeError(
            f"Current TimeSeries not available: HTTP {r.status_code} - {r.text}. "
            "Run onem2m_setup.py first."
        )

    if "m2m:ts" not in r.json():
        raise RuntimeError(
            "SensorAE/machine01/current exists but is not a TimeSeries."
        )

    print("[OK] current TimeSeries available")


def ensure_subscription():
    r = get_resource(SUB_PATH)

    if r.status_code == 200:
        sub = r.json().get("m2m:sub", {})

        if subscription_matches(sub):
            print("[SKIP] Subscription already exists and is correctly configured")
            print(f"[OK] Notifications -> {NOTIFICATION_URL}")
            return

        print("[INFO] Subscription exists but configuration is outdated")

        if not notification_server_is_running():
            raise RuntimeError(
                "The subscription must be updated, but the notification server "
                f"is not listening on {NOTIFICATION_URL}. "
                "Start 'python src\\notification_server.py' first."
            )

        body = {
            "m2m:sub": desired_subscription()
        }

        r = requests.put(
            f"{BASE_URL}/{SUB_PATH}",
            headers=headers(),
            json=body,
            timeout=10,
        )

        if r.status_code != 200:
            raise RuntimeError(
                f"Cannot update subscription: HTTP {r.status_code} - {r.text}"
            )

        print("[OK] Subscription updated")
        print(f"[OK] Notifications -> {NOTIFICATION_URL}")
        return

    if r.status_code != 404:
        raise RuntimeError(
            f"Cannot check subscription: HTTP {r.status_code} - {r.text}"
        )

    if not notification_server_is_running():
        raise RuntimeError(
            "Subscription does not exist yet and ACME must verify the notification "
            f"endpoint {NOTIFICATION_URL}. "
            "Start 'python src\\notification_server.py' first, then run this script again."
        )

    body = {
        "m2m:sub": {
            "rn": SUB_NAME,
            **desired_subscription(),
        }
    }

    r = requests.post(
        f"{BASE_URL}/{SUB_PARENT}",
        headers=headers(23),
        json=body,
        timeout=10,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create subscription: HTTP {r.status_code} - {r.text}"
        )

    print("[OK] Subscription created")
    print(f"[OK] Notifications -> {NOTIFICATION_URL}")


def main():
    print("ELEKTRA - idempotent oneM2M subscription setup")
    print("-" * 60)

    try:
        ensure_parent_exists()
        ensure_subscription()

    except requests.RequestException as exc:
        print(f"[ERROR] Cannot contact ACME MN-CSE: {exc}")
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print()
    print("[DONE] Subscription setup is ready.")
    print("The script can be safely executed again.")


if __name__ == "__main__":
    main()
