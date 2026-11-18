import os
import sys

import requests


MEC_APP_SUPPORT_BASE = os.getenv("MEC_APP_SUPPORT_BASE")
APP_INSTANCE_ID = os.getenv("MEC_APP_INSTANCE_ID")


def require_env(name, value):
    if not value:
        print(f"[ERROR] Environment variable {name} is not configured.")
        print("Configure the MEC Sandbox values in PowerShell before running this script.")
        sys.exit(1)


def main():
    require_env("MEC_APP_SUPPORT_BASE", MEC_APP_SUPPORT_BASE)
    require_env("MEC_APP_INSTANCE_ID", APP_INSTANCE_ID)

    url = f"{MEC_APP_SUPPORT_BASE}/applications/{APP_INSTANCE_ID}/confirm_ready"

    print("Confirming ELEKTRA MEC application readiness...")
    print(f"Application Instance ID: {APP_INSTANCE_ID}")
    print(f"POST {url}")
    print()

    try:
        response = requests.post(
            url,
            json={"indication": "READY"},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[ERROR] MEC request failed: {exc}")
        sys.exit(1)

    print(f"HTTP {response.status_code}")

    if response.status_code == 204:
        print("[OK] MEC application readiness confirmed.")
        return

    print("[ERROR] MEC readiness confirmation failed.")
    if response.text:
        print(response.text)
    sys.exit(1)


if __name__ == "__main__":
    main()
