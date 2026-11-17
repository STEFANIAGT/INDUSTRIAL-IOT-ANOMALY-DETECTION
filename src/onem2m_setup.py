import uuid
import requests

BASE_URL = "http://127.0.0.1:8080/cse-mn"

ADMIN = "CAdmin"
SENSOR_REGISTRATION_ORIGINATOR = "CSensorAE"

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
    else:
        h["Content-Type"] = "application/json"
    return h


def get_resource(path, originator=ADMIN):
    url = BASE_URL if not path else f"{BASE_URL}/{path}"
    return requests.get(url, headers=headers(originator), timeout=5)


def ensure_sensor_ae():
    r = get_resource("SensorAE", ADMIN)

    if r.status_code == 200:
        data = r.json().get("m2m:ae", {})
        aei = data.get("aei")
        if not aei:
            raise RuntimeError("SensorAE exists but no AE-ID (aei) was returned.")
        print(f"[SKIP] SensorAE already exists (aei={aei})")
        return aei

    if r.status_code != 404:
        raise RuntimeError(f"Cannot check SensorAE: HTTP {r.status_code} - {r.text}")

    body = {
        "m2m:ae": {
            "rn": "SensorAE",
            "api": "Norg.unimore.elektra.sensor",
            "rr": True,
            "srv": ["4"],
        }
    }

    r = requests.post(
        BASE_URL,
        headers=headers(SENSOR_REGISTRATION_ORIGINATOR, 2),
        json=body,
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(f"Cannot create SensorAE: HTTP {r.status_code} - {r.text}")

    data = r.json().get("m2m:ae", {})
    aei = data.get("aei")
    if not aei:
        raise RuntimeError("SensorAE created but no AE-ID (aei) was returned.")

    print(f"[OK] Created SensorAE (aei={aei})")
    return aei


def ensure_container(path, rn, originator):
    r = get_resource(path, ADMIN)

    if r.status_code == 200:
        data = r.json()
        if "m2m:cnt" not in data:
            raise RuntimeError(f"{path} exists but is not a Container (m2m:cnt).")
        print(f"[SKIP] {rn} already exists")
        return

    if r.status_code != 404:
        raise RuntimeError(f"Cannot check {path}: HTTP {r.status_code} - {r.text}")

    parent = path.rsplit("/", 1)[0]
    body = {"m2m:cnt": {"rn": rn, "mni": 100}}

    r = requests.post(
        f"{BASE_URL}/{parent}",
        headers=headers(originator, 3),
        json=body,
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(f"Cannot create {rn}: HTTP {r.status_code} - {r.text}")

    print(f"[OK] Created {rn}")


def ensure_timeseries(sensor, originator):
    path = f"SensorAE/machine01/{sensor}"
    r = get_resource(path, ADMIN)

    if r.status_code == 200:
        data = r.json()
        if "m2m:ts" not in data:
            raise RuntimeError(
                f"{path} exists but is not a TimeSeries (m2m:ts). "
                "Do not overwrite it automatically."
            )
        print(f"[SKIP] {sensor} TimeSeries already exists")
        return

    if r.status_code != 404:
        raise RuntimeError(f"Cannot check {path}: HTTP {r.status_code} - {r.text}")

    body = {"m2m:ts": {"rn": sensor, "mni": 100}}

    r = requests.post(
        f"{BASE_URL}/SensorAE/machine01",
        headers=headers(originator, 29),
        json=body,
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create {sensor} TimeSeries: HTTP {r.status_code} - {r.text}"
        )

    print(f"[OK] Created {sensor} TimeSeries")


def main():
    print("ELEKTRA - idempotent oneM2M sensor setup")
    print("-" * 60)

    try:
        r = get_resource("", ADMIN)
        if r.status_code != 200:
            raise RuntimeError(
                f"ACME MN-CSE is not reachable: HTTP {r.status_code} - {r.text}"
            )

        print("[OK] ACME MN-CSE reachable")

        sensor_aei = ensure_sensor_ae()
        ensure_container("SensorAE/machine01", "machine01", sensor_aei)

        for sensor in SENSORS:
            ensure_timeseries(sensor, sensor_aei)

    except requests.RequestException as exc:
        print(f"[ERROR] Cannot contact ACME MN-CSE: {exc}")
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print()
    print("[DONE] Sensor-side oneM2M setup is ready.")
    print("The script can be safely executed again.")


if __name__ == "__main__":
    main()
