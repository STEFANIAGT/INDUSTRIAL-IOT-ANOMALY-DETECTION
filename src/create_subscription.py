import uuid
import requests

BASE_URL = "http://127.0.0.1:8080/cse-mn"
ORIGINATOR = "CSensorAE"
NOTIFICATION_URL = "http://127.0.0.1:9999/notify"


def headers(resource_type=None):
    h = {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": f"req-{uuid.uuid4().hex[:8]}",
        "X-M2M-RVI": "4",
        "Accept": "application/json",
    }
    if resource_type is not None:
        h["Content-Type"] = f"application/json;ty={resource_type}"
    return h


def main():
    url = f"{BASE_URL}/SensorAE/machine01/current"

    body = {
        "m2m:sub": {
            "rn": "newReadingSubscription",
            "nu": [NOTIFICATION_URL],
            "enc": {"net": [3]},
            "nct": 1
        }
    }

    print("Creating oneM2M subscription...")
    r = requests.post(url, headers=headers(23), json=body, timeout=10)

    if r.status_code in (200, 201):
        print("[OK] Subscription created.")
        print(f"[OK] Notifications -> {NOTIFICATION_URL}")
        return

    if r.status_code == 409:
        print("[SKIP] Subscription already exists.")
        return

    print(f"[ERROR] HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
