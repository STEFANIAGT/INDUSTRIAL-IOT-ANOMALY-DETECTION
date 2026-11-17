import uuid
import requests

BASE_URL = "http://127.0.0.1:8080/cse-mn"
ADMIN = "CAdmin"
SENSOR_ORIGINATOR = "CSensorAE"
SENSORS = ("temperature", "vibration", "current")


def headers(originator, resource_type=None):
    h = {
        "X-M2M-Origin": originator,
        "X-M2M-RI": f"req-{uuid.uuid4().hex[:8]}",
        "X-M2M-RVI": "4",
        "Accept": "application/json",
    }
    if resource_type is not None:
        h["Content-Type"] = f"application/json;ty={resource_type}"
    return h


def create(url, resource_type, body, label, originator):
    r = requests.post(
        url,
        headers=headers(originator, resource_type),
        json=body,
        timeout=5,
    )

    if r.status_code in (200, 201):
        print(f"[OK] Created: {label}")
        try:
            return r.json()
        except ValueError:
            return None

    if r.status_code == 409:
        print(f"[SKIP] Already exists: {label}")
        return None

    print(f"[ERROR] {label}: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def main():
    print("Checking ACME...")
    r = requests.get(BASE_URL, headers=headers(ADMIN), timeout=5)
    if r.status_code != 200:
        print("Cannot reach ACME.")
        print("HTTP:", r.status_code)
        print(r.text)
        raise SystemExit(1)

    print("[OK] ACME MN-CSE reachable")

    response = create(
        BASE_URL,
        2,
        {
            "m2m:ae": {
                "rn": "SensorAE",
                "api": "Norg.unimore.elektra.sensor",
                "rr": True,
                "srv": ["4"]
            }
        },
        "SensorAE",
        SENSOR_ORIGINATOR
    )

    sensor_aei = SENSOR_ORIGINATOR
    if isinstance(response, dict):
        sensor_aei = response.get("m2m:ae", {}).get("aei", SENSOR_ORIGINATOR)

    sensor_ae_url = f"{BASE_URL}/SensorAE"

    create(
        sensor_ae_url,
        3,
        {"m2m:cnt": {"rn": "machine01", "mni": 100}},
        "machine01",
        sensor_aei
    )

    machine_url = f"{sensor_ae_url}/machine01"

    for sensor in SENSORS:
        create(
            machine_url,
            29,
            {"m2m:ts": {"rn": sensor, "mni": 100}},
            f"{sensor} TimeSeries",
            sensor_aei
        )

    print()
    print("Expected oneM2M tree:")
    print("cse-mn")
    print("└── SensorAE")
    print("    └── machine01")
    print("        ├── temperature (TimeSeries)")
    print("        ├── vibration   (TimeSeries)")
    print("        └── current     (TimeSeries)")


if __name__ == "__main__":
    main()
