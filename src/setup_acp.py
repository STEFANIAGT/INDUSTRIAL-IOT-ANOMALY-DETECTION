import uuid
import requests

BASE_URL = "http://127.0.0.1:8080/cse-mn"

ADMIN = "CAdmin"
SENSOR_AE = "CSensorAE"
ANOMALY_AE = "CAnomalyDetectionAE"

SENSORS = ("temperature", "vibration", "current")


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


def get_resource(path, originator):
    return requests.get(
        f"{BASE_URL}/{path}",
        headers=headers(originator),
        timeout=5,
    )


def create_or_update_acp(rn, privileges, self_privileges):
    body = {
        "m2m:acp": {
            "pv": {"acr": privileges},
            "pvs": {"acr": self_privileges},
        }
    }

    existing = get_resource(rn, ADMIN)

    if existing.status_code == 200:
        r = requests.put(
            f"{BASE_URL}/{rn}",
            headers=headers(ADMIN),
            json=body,
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()["m2m:acp"]
            print(f"[OK] Updated ACP: {rn}")
            return data["ri"]

        print(f"[ERROR] Cannot update ACP {rn}: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    if existing.status_code != 404:
        print(f"[ERROR] Cannot check ACP {rn}: HTTP {existing.status_code}")
        print(existing.text)
        raise SystemExit(1)

    create_body = {
        "m2m:acp": {
            "rn": rn,
            "pv": {"acr": privileges},
            "pvs": {"acr": self_privileges},
        }
    }

    r = requests.post(
        BASE_URL,
        headers=headers(ADMIN, 1),
        json=create_body,
        timeout=5,
    )

    if r.status_code in (200, 201):
        data = r.json()["m2m:acp"]
        print(f"[OK] Created ACP: {rn}")
        return data["ri"]

    print(f"[ERROR] Cannot create ACP {rn}: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def assign_acp(path, wrapper, acp_ri, originator):
    body = {
        wrapper: {
            "acpi": [acp_ri]
        }
    }

    r = requests.put(
        f"{BASE_URL}/{path}",
        headers=headers(originator),
        json=body,
        timeout=5,
    )

    if r.status_code == 200:
        print(f"[OK] ACP assigned to: {path}")
        return

    print(
        f"[ERROR] Cannot assign ACP to {path}: "
        f"HTTP {r.status_code} (originator={originator})"
    )
    print(r.text)
    raise SystemExit(1)


def check_get(path, originator, expected_allowed, label):
    r = get_resource(path, originator)
    allowed = r.status_code == 200

    if allowed == expected_allowed:
        print(f"[OK] {label}: {'ALLOWED' if allowed else 'DENIED'}")
        return True

    print(
        f"[ERROR] {label}: HTTP {r.status_code}; "
        f"expected {'ALLOWED' if expected_allowed else 'DENIED'}"
    )
    print(r.text)
    return False


def main():
    print("Configuring oneM2M Access Control Policies...")
    print()

    # Sensor data policy:
    # CREATE=1, RETRIEVE=2, therefore CREATE+RETRIEVE=3.
    sensor_acp_ri = create_or_update_acp(
        "sensorDataACP",
        privileges=[
            {"acor": [SENSOR_AE], "acop": 3},
            {"acor": [ANOMALY_AE], "acop": 2},
            {"acor": [ADMIN], "acop": 63},
        ],
        self_privileges=[
            {"acor": [SENSOR_AE], "acop": 63},
            {"acor": [ADMIN], "acop": 63},
        ],
    )

    # Alert policy.
    alerts_acp_ri = create_or_update_acp(
        "alertsACP",
        privileges=[
            {"acor": [ANOMALY_AE], "acop": 3},
            {"acor": [ADMIN], "acop": 63},
        ],
        self_privileges=[
            {"acor": [ANOMALY_AE], "acop": 63},
            {"acor": [ADMIN], "acop": 63},
        ],
    )

    print()
    print("Assigning policies with the resource owner originators...")

    for sensor in SENSORS:
        assign_acp(
            f"SensorAE/machine01/{sensor}",
            "m2m:ts",
            sensor_acp_ri,
            SENSOR_AE,
        )

    assign_acp(
        "AnomalyDetectionAE/alerts",
        "m2m:cnt",
        alerts_acp_ri,
        ANOMALY_AE,
    )

    print()
    print("Checking permissions...")

    checks = [
        check_get(
            "SensorAE/machine01/temperature",
            SENSOR_AE,
            True,
            "SensorAE can read sensor data",
        ),
        check_get(
            "SensorAE/machine01/temperature",
            ANOMALY_AE,
            True,
            "AnomalyDetectionAE can read sensor data",
        ),
        check_get(
            "AnomalyDetectionAE/alerts",
            SENSOR_AE,
            False,
            "SensorAE cannot read alerts",
        ),
        check_get(
            "AnomalyDetectionAE/alerts",
            ANOMALY_AE,
            True,
            "AnomalyDetectionAE can read alerts",
        ),
    ]

    print()
    if all(checks):
        print("DONE. ACP configuration is active.")
    else:
        print("ACP assignment completed, but a permission check failed.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
