import uuid
import requests

BASE_URL = "http://127.0.0.1:8080/cse-mn"

ADMIN = "CAdmin"
SENSOR_AE = "CSensorAE"
ANOMALY_REGISTRATION_ORIGINATOR = "CAnomalyDetectionAE"

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


def get_resource(path, originator=ADMIN):
    return requests.get(
        f"{BASE_URL}/{path}",
        headers=headers(originator),
        timeout=5,
    )


def ensure_anomaly_ae():
    r = get_resource("AnomalyDetectionAE", ADMIN)

    if r.status_code == 200:
        ae = r.json().get("m2m:ae", {})
        aei = ae.get("aei")
        if not aei:
            raise RuntimeError(
                "AnomalyDetectionAE exists but no AE-ID (aei) was returned."
            )
        print(f"[SKIP] AnomalyDetectionAE already exists (aei={aei})")
        return aei

    if r.status_code != 404:
        raise RuntimeError(
            f"Cannot check AnomalyDetectionAE: HTTP {r.status_code} - {r.text}"
        )

    body = {
        "m2m:ae": {
            "rn": "AnomalyDetectionAE",
            "api": "Norg.unimore.elektra.anomaly",
            "rr": True,
            "srv": ["4"],
        }
    }

    r = requests.post(
        BASE_URL,
        headers=headers(ANOMALY_REGISTRATION_ORIGINATOR, 2),
        json=body,
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create AnomalyDetectionAE: HTTP {r.status_code} - {r.text}"
        )

    ae = r.json().get("m2m:ae", {})
    aei = ae.get("aei")
    if not aei:
        raise RuntimeError(
            "AnomalyDetectionAE created but no AE-ID (aei) was returned."
        )

    print(f"[OK] Created AnomalyDetectionAE (aei={aei})")
    return aei


def ensure_alerts_container(anomaly_aei):
    r = get_resource("AnomalyDetectionAE/alerts", ADMIN)

    if r.status_code == 200:
        if "m2m:cnt" not in r.json():
            raise RuntimeError(
                "AnomalyDetectionAE/alerts exists but is not a Container."
            )
        print("[SKIP] alerts container already exists")
        return

    if r.status_code != 404:
        raise RuntimeError(
            f"Cannot check alerts container: HTTP {r.status_code} - {r.text}"
        )

    body = {
        "m2m:cnt": {
            "rn": "alerts",
            "mni": 100,
        }
    }

    r = requests.post(
        f"{BASE_URL}/AnomalyDetectionAE",
        headers=headers(anomaly_aei, 3),
        json=body,
        timeout=5,
    )

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create alerts container: HTTP {r.status_code} - {r.text}"
        )

    print("[OK] Created alerts container")


def ensure_acp(rn, privileges, self_privileges):
    existing = get_resource(rn, ADMIN)

    body = {
        "m2m:acp": {
            "pv": {"acr": privileges},
            "pvs": {"acr": self_privileges},
        }
    }

    if existing.status_code == 200:
        r = requests.put(
            f"{BASE_URL}/{rn}",
            headers=headers(ADMIN),
            json=body,
            timeout=5,
        )

        if r.status_code != 200:
            raise RuntimeError(
                f"Cannot update {rn}: HTTP {r.status_code} - {r.text}"
            )

        acp = r.json().get("m2m:acp", {})
        ri = acp.get("ri")
        if not ri:
            raise RuntimeError(f"{rn} updated but no resource ID was returned.")

        print(f"[OK] Updated ACP: {rn}")
        return ri

    if existing.status_code != 404:
        raise RuntimeError(
            f"Cannot check {rn}: HTTP {existing.status_code} - {existing.text}"
        )

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

    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Cannot create {rn}: HTTP {r.status_code} - {r.text}"
        )

    acp = r.json().get("m2m:acp", {})
    ri = acp.get("ri")
    if not ri:
        raise RuntimeError(f"{rn} created but no resource ID was returned.")

    print(f"[OK] Created ACP: {rn}")
    return ri


def assign_acp(path, wrapper, acp_ri, originator):
    r = get_resource(path, ADMIN)

    if r.status_code != 200:
        raise RuntimeError(
            f"Cannot retrieve {path}: HTTP {r.status_code} - {r.text}"
        )

    resource = r.json().get(wrapper, {})
    current_acpi = resource.get("acpi", [])

    if current_acpi == [acp_ri]:
        print(f"[SKIP] Correct ACP already assigned to: {path}")
        return

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

    if r.status_code != 200:
        raise RuntimeError(
            f"Cannot assign ACP to {path}: "
            f"HTTP {r.status_code} - {r.text}"
        )

    print(f"[OK] ACP assigned to: {path}")


def check_get(path, originator, expected_allowed, label):
    r = get_resource(path, originator)
    allowed = r.status_code == 200

    if allowed != expected_allowed:
        expected = "ALLOWED" if expected_allowed else "DENIED"
        raise RuntimeError(
            f"{label}: HTTP {r.status_code}, expected {expected}. {r.text}"
        )

    print(f"[OK] {label}: {'ALLOWED' if allowed else 'DENIED'}")


def main():
    print("ELEKTRA - idempotent oneM2M ACP setup")
    print("-" * 60)

    try:
        r = requests.get(
            BASE_URL,
            headers=headers(ADMIN),
            timeout=5,
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"ACME MN-CSE is not reachable: HTTP {r.status_code} - {r.text}"
            )

        print("[OK] ACME MN-CSE reachable")

        # SensorAE and sensor TimeSeries must be created by onem2m_setup.py first.
        for sensor in SENSORS:
            r = get_resource(f"SensorAE/machine01/{sensor}", ADMIN)
            if r.status_code != 200 or "m2m:ts" not in r.json():
                raise RuntimeError(
                    f"Missing sensor TimeSeries: {sensor}. "
                    "Run onem2m_setup.py first."
                )

        anomaly_aei = ensure_anomaly_ae()
        ensure_alerts_container(anomaly_aei)

        sensor_acp_ri = ensure_acp(
            "sensorDataACP",
            privileges=[
                {"acor": [SENSOR_AE], "acop": 3},
                {"acor": [anomaly_aei], "acop": 2},
                {"acor": [ADMIN], "acop": 63},
            ],
            self_privileges=[
                {"acor": [SENSOR_AE], "acop": 63},
                {"acor": [ADMIN], "acop": 63},
            ],
        )

        alerts_acp_ri = ensure_acp(
            "alertsACP",
            privileges=[
                {"acor": [anomaly_aei], "acop": 3},
                {"acor": [ADMIN], "acop": 63},
            ],
            self_privileges=[
                {"acor": [anomaly_aei], "acop": 63},
                {"acor": [ADMIN], "acop": 63},
            ],
        )

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
            anomaly_aei,
        )

        print()
        print("Checking permissions...")

        check_get(
            "SensorAE/machine01/temperature",
            SENSOR_AE,
            True,
            "SensorAE can read sensor data",
        )

        check_get(
            "SensorAE/machine01/temperature",
            anomaly_aei,
            True,
            "AnomalyDetectionAE can read sensor data",
        )

        check_get(
            "AnomalyDetectionAE/alerts",
            SENSOR_AE,
            False,
            "SensorAE cannot read alerts",
        )

        check_get(
            "AnomalyDetectionAE/alerts",
            anomaly_aei,
            True,
            "AnomalyDetectionAE can read alerts",
        )

    except requests.RequestException as exc:
        print(f"[ERROR] Cannot contact ACME MN-CSE: {exc}")
        raise SystemExit(1)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print()
    print("[DONE] ACP configuration is ready.")
    print("The script can be safely executed again.")


if __name__ == "__main__":
    main()

