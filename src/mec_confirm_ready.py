import requests

MEC_BASE = "https://try-mec.etsi.org/sbxr49ri7d/mep1/mec_app_support/v2"
APP_INSTANCE_ID = "1824d9cb-41bb-4f68-a312-09e3bcf99a1c"


def main():
    url = f"{MEC_BASE}/applications/{APP_INSTANCE_ID}/confirm_ready"
    body = {"indication": "READY"}

    print("Confirming ELEKTRA MEC application readiness...")
    print(f"Application Instance ID: {APP_INSTANCE_ID}")
    print(f"POST {url}")
    print()

    try:
        response = requests.post(
            url,
            json=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[ERROR] Cannot contact ETSI MEC Sandbox: {exc}")
        raise SystemExit(1)

    print(f"HTTP {response.status_code}")

    if response.status_code == 204:
        print("[OK] MEC application confirmed READY on mep1.")
        print("[OK] elektra-anomaly-ae is now initialized as a MEC Application.")
        return

    print("[ERROR] MEC readiness confirmation failed.")
    if response.text:
        print(response.text)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
