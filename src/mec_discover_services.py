import requests

MEC_SERVICE_MGMT_BASE = "https://try-mec.etsi.org/sbxr49ri7d/mep1/mec_service_mgmt/v1"
APP_INSTANCE_ID = "1824d9cb-41bb-4f68-a312-09e3bcf99a1c"


def main():
    url = f"{MEC_SERVICE_MGMT_BASE}/services"

    print("Discovering MEC services available on mep1...")
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
        print(f"[ERROR] Cannot contact ETSI MEC Sandbox: {exc}")
        raise SystemExit(1)

    print(f"HTTP {response.status_code}")

    if response.status_code != 200:
        print("[ERROR] MEC service discovery failed.")
        if response.text:
            print(response.text)
        raise SystemExit(1)

    try:
        data = response.json()
    except ValueError:
        print("[ERROR] MEC Sandbox returned a non-JSON response.")
        print(response.text)
        raise SystemExit(1)

    services = data if isinstance(data, list) else data.get("serviceInfo", data)

    print("[OK] MEC service discovery succeeded.")
    print()

    if isinstance(services, list):
        print(f"Services discovered: {len(services)}")
        for service in services:
            if not isinstance(service, dict):
                print(f" - {service}")
                continue
            name = service.get("serName", "unknown")
            state = service.get("state", "unknown")
            version = service.get("version", "unknown")
            instance_id = service.get("serInstanceId", "unknown")
            print(
                f" - {name} | state={state} | version={version} | "
                f"id={instance_id}"
            )
    else:
        print(services)

    print()
    print("DONE. elektra-anomaly-ae can interact with MEC Service Management.")


if __name__ == "__main__":
    main()
