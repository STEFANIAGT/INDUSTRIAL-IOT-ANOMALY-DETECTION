import time
import uuid
from datetime import datetime, timezone

import requests

from sensor_simulator import normal_reading, anomalous_reading

BASE_URL = "http://127.0.0.1:8080/cse-mn"
ORIGINATOR = "CSensorAE"


def headers():
    return {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": f"req-{uuid.uuid4().hex[:8]}",
        "X-M2M-RVI": "4",
        "Content-Type": "application/json;ty=30",
        "Accept": "application/json",
    }


def oneM2M_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def publish(sensor_name, value, data_generation_time):
    url = f"{BASE_URL}/SensorAE/machine01/{sensor_name}"

    body = {
        "m2m:tsi": {
            "dgt": data_generation_time,
            "con": value
        }
    }

    r = requests.post(url, headers=headers(), json=body, timeout=5)

    if r.status_code not in (200, 201):
        print(f"[ERROR] {sensor_name}: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)


def main():
    print("Publishing simulated motor data as oneM2M TimeSeriesInstances...")
    print("-" * 78)

    for i in range(1, 11):
        injected = (i % 5 == 0)
        reading = anomalous_reading() if injected else normal_reading()
        d = reading.as_dict()

        dgt = oneM2M_timestamp()

        publish("temperature", d["temperature"], dgt)
        publish("vibration", d["vibration"], dgt)
        publish("current", d["current"], dgt)

        label = "ANOMALOUS TEST READING" if injected else "normal"
        print(
            f"#{i:02d}  "
            f"T={d['temperature']:.2f} C | "
            f"V={d['vibration']:.3f} | "
            f"I={d['current']:.2f} A  -> TimeSeries published ({label})"
        )

        time.sleep(1.05)

    print()
    print("DONE. Data stored as oneM2M TimeSeriesInstances.")


if __name__ == "__main__":
    main()
