import os
import sys

import requests


MEC_SERVICE_MGMT_BASE = os.getenv("MEC_SERVICE_MGMT_BASE")
APP_INSTANCE_ID = os.getenv("MEC_APP_INSTANCE_ID")


def require_env(name, value):
    if not value:
        print(f"[ERROR] Environment variable {name} is not configured.")
        print("Configure the MEC Sandbox values in PowerShell before running this script.")
        sys.exit(1)


def main():
    require_env("MEC_SERVICE_MGMT_BASE", MEC_SERVICE_MGMT_BASE)

    url = f"{MEC_SERVICE_MGMT_BASE}/services"

    print("Discovering MEC services available on mep1...")
    if APP_INSTANCE_ID:
        print(f"Application Instance ID: {APP_INSTANCE_ID}")
    print(f"GET {url}")
    print()

    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[ERROR] MEC service discovery failed: {exc}")
        sys.exit(1)

    print(f"HTTP {response.status_code}")

    if response.status_code != 200:
        print("[ERROR] MEC service discovery failed.")
        if response.text:
            print(response.text)
        sys.exit(1)

    try:
        data = response.json()
    except ValueError:
        print("[ERROR] MEC Sandbox returned a non-JSON response.")
        print(response.text)
        sys.exit(1)

    services = data if isinstance(data, list) else data.get("services", [])

    print(f"[OK] Discovered {len(services)} MEC service(s).")

    for index, service in enumerate(services, start=1):
        if not isinstance(service, dict):
            print(f"  {index}. {service}")
            continue

        name = (
            service.get("serName")
            or service.get("name")
            or service.get("serInstanceId")
            or "Unnamed service"
        )

        state = service.get("state") or service.get("serAvailability") or "unknown"
        version = service.get("version")

        details = [f"name={name}", f"state={state}"]
        if version is not None:
            details.append(f"version={version}")

        print(f"  {index}. " + " | ".join(details))


if __name__ == "__main__":
    main()

