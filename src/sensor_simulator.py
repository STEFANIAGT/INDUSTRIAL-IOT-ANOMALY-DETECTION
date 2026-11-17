import random
from dataclasses import dataclass
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAINING_FILE = PROJECT_ROOT / "data" / "training_normal.csv"

@dataclass
class Reading:
    temperature: float
    vibration: float
    current: float
    injected_anomaly: bool = False

    def as_dict(self):
        return {
            "temperature": round(self.temperature, 3),
            "vibration": round(self.vibration, 3),
            "current": round(self.current, 3),
            "injected_anomaly": self.injected_anomaly,
        }

def normal_reading():
    # Synthetic baseline for an industrial electric motor.
    load = random.gauss(0.0, 1.0)
    temperature = 68.0 + 2.0 * load + random.gauss(0, 1.2)
    current = 8.0 + 0.45 * load + random.gauss(0, 0.20)
    vibration = 0.32 + 0.025 * abs(load) + random.gauss(0, 0.025)

    return Reading(
        temperature=temperature,
        vibration=max(vibration, 0.05),
        current=max(current, 0.5),
        injected_anomaly=False,
    )

def anomalous_reading():
    r = normal_reading()
    kind = random.choice(["bearing", "overheat", "overcurrent", "mixed"])

    if kind == "bearing":
        r.vibration += random.uniform(1.20, 2.00)
    elif kind == "overheat":
        r.temperature += random.uniform(20, 35)
    elif kind == "overcurrent":
        r.current += random.uniform(4.0, 7.0)
    else:
        r.vibration += random.uniform(0.90, 1.50)
        r.temperature += random.uniform(15, 25)
        r.current += random.uniform(3.0, 5.0)

    r.injected_anomaly = True
    return r

def generate_training_data(rows=1500):
    TRAINING_FILE.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for _ in range(rows):
        d = normal_reading().as_dict()
        records.append({
            "temperature": d["temperature"],
            "vibration": d["vibration"],
            "current": d["current"],
        })

    pd.DataFrame(records).to_csv(TRAINING_FILE, index=False)
    print(f"Created {rows} normal readings in {TRAINING_FILE}")

if __name__ == "__main__":
    generate_training_data()
