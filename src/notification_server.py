import json
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import joblib
import pandas as pd
import requests

ACME_BASE = "http://127.0.0.1:8080/cse-mn"
ADMIN = "CAdmin"
ANOMALY_ORIGINATOR = "CAnomalyDetectionAE"
PORT = 9999

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
FEATURES = ["temperature", "vibration", "current"]

processed_notifications = set()
_model_cache = {"file": None, "version": None, "model": None}


def onem2m_headers(originator, resource_type=None):
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


def resource_exists(path, originator=ADMIN):
    r = requests.get(
        f"{ACME_BASE}/{path}",
        headers=onem2m_headers(originator),
        timeout=5,
    )
    if r.status_code == 200:
        return True
    if r.status_code == 404:
        return False
    raise RuntimeError(f"Cannot check {path}: {r.status_code} {r.text}")


def read_latest(sensor_name):
    url = f"{ACME_BASE}/SensorAE/machine01/{sensor_name}/la"
    r = requests.get(
        url,
        headers=onem2m_headers(ANOMALY_ORIGINATOR),
        timeout=5,
    )
    r.raise_for_status()

    data = r.json()
    if "m2m:tsi" in data:
        return float(data["m2m:tsi"]["con"])
    if "m2m:cin" in data:
        return float(data["m2m:cin"]["con"])

    raise RuntimeError(f"Unexpected latest resource for {sensor_name}: {data}")


def get_active_model_metadata():
    r = requests.get(
        f"{ACME_BASE}/model/la",
        headers=onem2m_headers(ANOMALY_ORIGINATOR),
        timeout=5,
    )
    r.raise_for_status()

    con = r.json().get("m2m:cin", {}).get("con")
    if not isinstance(con, dict):
        raise RuntimeError("Active model metadata is missing or invalid.")

    return con


def load_active_model():
    metadata = get_active_model_metadata()
    filename = Path(metadata.get("file", "anomaly_model.joblib")).name
    version = metadata.get("version", "unknown")

    if (
        _model_cache["model"] is not None
        and _model_cache["file"] == filename
        and _model_cache["version"] == version
    ):
        return _model_cache["model"], metadata

    model_path = MODELS_DIR / filename

    if not model_path.exists():
        raise RuntimeError(f"Active model file not found: {model_path}")

    model = joblib.load(model_path)

    _model_cache["file"] = filename
    _model_cache["version"] = version
    _model_cache["model"] = model

    print(f"[MODEL] Loaded active model {version}: {filename}")
    return model, metadata


def ensure_anomaly_ae_and_alerts():
    if not resource_exists("AnomalyDetectionAE"):
        body = {
            "m2m:ae": {
                "rn": "AnomalyDetectionAE",
                "api": "Norg.unimore.elektra.anomaly",
                "rr": True,
                "srv": ["4"],
            }
        }
        r = requests.post(
            ACME_BASE,
            headers=onem2m_headers(ANOMALY_ORIGINATOR, 2),
            json=body,
            timeout=5,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(
                f"Cannot create AnomalyDetectionAE: {r.status_code} {r.text}"
            )

    if not resource_exists("AnomalyDetectionAE/alerts", ANOMALY_ORIGINATOR):
        body = {"m2m:cnt": {"rn": "alerts", "mni": 100}}
        r = requests.post(
            f"{ACME_BASE}/AnomalyDetectionAE",
            headers=onem2m_headers(ANOMALY_ORIGINATOR, 3),
            json=body,
            timeout=5,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(
                f"Cannot create alerts container: {r.status_code} {r.text}"
            )


def create_alert(score, values, model_metadata):
    body = {
        "m2m:cin": {
            "con": {
                "machine": "machine01",
                "status": "ANOMALY",
                "score": round(score, 3),
                "modelVersion": model_metadata.get("version", "unknown"),
                "readings": values,
            }
        }
    }
    r = requests.post(
        f"{ACME_BASE}/AnomalyDetectionAE/alerts",
        headers=onem2m_headers(ANOMALY_ORIGINATOR, 4),
        json=body,
        timeout=5,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Cannot create alert: {r.status_code} {r.text}")


def run_inference():
    values = {sensor: read_latest(sensor) for sensor in FEATURES}
    model, model_metadata = load_active_model()

    X = pd.DataFrame([values])[FEATURES]
    prediction = int(model.predict(X)[0])
    score = float(model.decision_function(X)[0])
    status = "ANOMALY" if prediction == -1 else "NORMAL"

    print(
        f"[AI] T={values['temperature']:.2f} C | "
        f"V={values['vibration']:.3f} | "
        f"I={values['current']:.2f} A | "
        f"score={score:+.3f} | {status} | "
        f"model={model_metadata.get('version', 'unknown')}"
    )

    if status == "ANOMALY":
        ensure_anomaly_ae_and_alerts()
        create_alert(score, values, model_metadata)
        print("[ALERT] Saved automatically in oneM2M.")


class NotificationHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"

        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            payload = {}

        request_id = self.headers.get("X-M2M-RI", "")

        self.send_response(200)
        self.send_header("X-M2M-RSC", "2000")
        if request_id:
            self.send_header("X-M2M-RI", request_id)
        self.send_header("X-M2M-RVI", "4")
        self.send_header("Content-Length", "0")
        self.end_headers()

        signal = payload.get("m2m:sgn", {})

        if signal.get("vrq") is True:
            print("[SUB] Verification request received and accepted.")
            return

        rep = signal.get("nev", {}).get("rep", {})
        instance = {}
        if isinstance(rep, dict):
            instance = rep.get("m2m:tsi", {}) or rep.get("m2m:cin", {})

        event_ri = instance.get("ri")

        if event_ri and event_ri in processed_notifications:
            print(f"[SUB] Duplicate notification ignored: {event_ri}")
            return

        if event_ri:
            processed_notifications.add(event_ri)

        print("[SUB] New oneM2M notification received.")
        try:
            run_inference()
        except Exception as exc:
            print(f"[ERROR] Automatic inference failed: {exc}")

    def log_message(self, format, *args):
        return


def main():
    print("ELEKTRA - Anomaly Detection AE notification server")
    print("Sensor storage: oneM2M TimeSeries / TimeSeriesInstance")
    print("Model selection: active version from MN-CSE /model")
    print(f"Listening on http://127.0.0.1:{PORT}/notify")
    print("Keep this PowerShell open. Press Ctrl+C to stop.")
    print("-" * 78)

    server = HTTPServer(("127.0.0.1", PORT), NotificationHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nNotification server stopped.")


if __name__ == "__main__":
    main()
