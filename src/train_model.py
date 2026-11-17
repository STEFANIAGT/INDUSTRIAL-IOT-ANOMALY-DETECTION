from pathlib import Path
import joblib
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from sensor_simulator import TRAINING_FILE, generate_training_data

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_FILE = PROJECT_ROOT / "models" / "anomaly_model.joblib"
FEATURES = ["temperature", "vibration", "current"]

if not TRAINING_FILE.exists():
    generate_training_data()

df = pd.read_csv(TRAINING_FILE)
X = df[FEATURES]

# One-Class SVM learns the region occupied by NORMAL motor behaviour.
# The RBF kernel is useful here because readings far outside the learned
# normal region are clearly classified as anomalies.
model = Pipeline([
    ("scale", StandardScaler()),
    ("one_class_svm", OneClassSVM(
        kernel="rbf",
        gamma="scale",
        nu=0.01
    )),
])

model.fit(X)

MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
joblib.dump(model, MODEL_FILE)

print(f"Training completed on {len(df)} normal readings.")
print("Model: One-Class SVM")
print(f"Model saved to {MODEL_FILE}")
