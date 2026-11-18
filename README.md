# INDUSTRIAL-IOT-ANOMALY-DETECTION with oneM2M and ETSI MEC

IoT hackathon project for monitoring an industrial motor using temperature, vibration and current sensors with oneM2M data collection, ETSI MEC edge computing and AI anomaly detection.

# Industrial IoT Anomaly Detection

An Industrial IoT prototype for detecting anomalous operating conditions in an electric motor.

The project combines:

- **oneM2M** for sensor data management, subscriptions, access control, and inter-CSE communication.
- **Machine Learning** for anomaly detection at the edge.
- **Centralized model management** for model versioning and cloud-to-edge deployment.
- **ETSI MEC Sandbox** integration for MEC application enablement and service discovery.

The current prototype uses simulated motor measurements for three parameters:

- Temperature
- Vibration
- Current

A **One-Class SVM** model is trained using normal operating data. The model is then deployed to the edge-side application, which performs anomaly detection. When an anomaly is detected, an alert is automatically stored in oneM2M.

---

## Architecture

```
                         CLOUD / CENTRAL
                   +-----------------------+
                   |        IN-CSE         |
                   |        id-in          |
                   |                       |
                   |     ModelManagerAE    |
                   |       └── modelRepo   |
                   |           └── anomalyModel
                   |               ├── v1  |
                   |               └── v2  |
                   +-----------+-----------+
                               |
                               | Mcc
                               |
                   +-----------v-----------+
                   |        MN-CSE         |
                   |        id-mn          |
                   |                       |
                   |       SensorAE        |
                   |       └── machine01   |
                   |           ├── temperature
                   |           ├── vibration
                   |           └── current |
                   |                       |
                   |         model         |
                   |       └── active version
                   |                       |
                   |   AnomalyDetectionAE  |
                   |       └── alerts      |
                   +-----------+-----------+
                               |
                               | Mca
                               |
                   +-----------v-----------+
                   | Edge-side application |
                   |                       |
                   | Notification handling |
                   | Active model loading  |
                   | Anomaly inference     |
                   +-----------------------+

                           ETSI MEC
                   +-----------------------+
                   | MEC Sandbox / mep1    |
                   |                       |
                   | MEC application       |
                   | MEC011 READY           |
                   | Service discovery     |
                   +-----------------------+

```

The oneM2M architecture manages sensor data, subscriptions, access control, and model distribution. The ETSI MEC Sandbox is used to demonstrate MEC application enablement and service discovery.

---

## Main Features

### 1. oneM2M Sensor Management

Motor measurements are stored as oneM2M **TimeSeries** resources.

```
SensorAE
└── machine01
    ├── temperature
    ├── vibration
    └── current

```

Each sensor measurement is stored as a **TimeSeriesInstance**.

### 2. Event-Driven Anomaly Detection

A oneM2M subscription is attached to the `current` TimeSeries.

The publisher sends temperature, vibration, and current measurements sequentially. The `current` measurement is published last for each complete motor sample. Therefore, its notification triggers the inference process after the other two measurements have been published.

The processing flow is:

```
New motor sample
       |
       v
oneM2M TimeSeries
       |
       v
Subscription notification
       |
       v
AnomalyDetectionAE
       |
       v
Machine Learning inference
       |
       v
NORMAL / ANOMALY
       |
       v
oneM2M alert

```

### 3. Access Control Policies

The prototype uses different **Access Control Policies (ACPs)** to implement access restrictions.

The intended permissions are:

- `sensorDataACP`
  - `CSensorAE`: CREATE and RETRIEVE
  - `CAnomalyDetectionAE`: RETRIEVE
  - `CAdmin`: full access
- `alertsACP`
  - `CAnomalyDetectionAE`: CREATE and RETRIEVE
  - `CAdmin`: full access
- `modelACP`
  - `CAnomalyDetectionAE`: RETRIEVE
  - `CAdmin`: full access
- `cloudModelRepoACP`
  - Allows the MN-CSE to retrieve model versions from the IN-CSE.

These policies separate sensor data access, alert creation, and model retrieval.

### 4. Model Versioning and Cloud-to-Edge Deployment

The central IN-CSE contains the model repository:

```
ModelManagerAE
└── modelRepo
    └── anomalyModel
        ├── v1
        └── v2

```

The deployment process is:

```
Central training / tuning
          |
          v
IN-CSE model repository
          |
          v
Model v2 + SHA-256 + Base64 payload
          |
          v
Retrieval through MN-CSE (Mcc)
          |
          v
SHA-256 integrity verification
          |
          v
models/anomaly_model_v2.joblib
          |
          v
MN-CSE /model
          |
          v
version=v2, status=active

```

The anomaly detection application reads the active model metadata from the MN-CSE `/model` resource and loads the corresponding model file.

This allows the active model version to be changed without modifying the inference application.

### 5. ETSI MEC Sandbox Integration

A MEC application instance was created in the ETSI MEC Sandbox on `mep1`.

The prototype includes the following MEC API interactions:

**MEC011 – Application Support**

- Calls the `confirm_ready` endpoint.
- Sends the `READY` indication.
- Expected response: `HTTP 204 No Content`.

**MEC011 – Service Management**

- Calls the service discovery endpoint.
- Retrieves the available MEC services.
- Expected response: `HTTP 200 OK`.

These operations demonstrate interaction between the application and the ETSI MEC platform.

The current prototype uses oneM2M for the sensor data and model management data plane, while the MEC Sandbox integration covers application enablement and service discovery. The MEC API interactions should not be interpreted as proof that the ML inference process is already running inside the MEC host.

---

## Project Structure

```
INDUSTRIAL-IOT-ANOMALY-DETECTION/
├── data/
│   └── training_normal.csv
├── in-cse-runtime/
│   └── acme.example.ini
├── models/
│   ├── anomaly_model.joblib
│   └── anomaly_model_v2.joblib
├── src/
│   ├── create_subscription.py
│   ├── deploy_model_v2_to_edge.py
│   ├── mec_confirm_ready.py
│   ├── mec_discover_services.py
│   ├── notification_server.py
│   ├── onem2m_setup.py
│   ├── publish_sensor_data.py
│   ├── sensor_simulator.py
│   ├── setup_acp.py
│   ├── setup_cloud_model_repo.py
│   ├── setup_cloud_repo_acp.py
│   ├── setup_model_resource.py
│   ├── train_model.py
│   └── tune_model_v2.py
├── .gitignore
├── acme.example.ini
├── README.md
└── requirements.txt

```

---

## Requirements

The prototype was developed and tested with:

- Python 3.12
- ACME oneM2M CSE

Python dependencies are listed in `requirements.txt`:

```
numpy
pandas
scikit-learn
joblib
requests
acmecse

```

---

## Installation

### 1. Create a virtual environment

```
python -m venv .venv
```

### 2. Activate the environment (PowerShell)

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```
pip install -r requirements.txt
```

### 4. Create the local ACME configuration files

The repository contains example ACME configuration files. Copy them before starting the CSEs:

```powershell
Copy-Item acme.example.ini acme.ini
Copy-Item .\in-cse-runtime\acme.example.ini .\in-cse-runtime\acme.ini
```

The local `acme.ini` files are used as runtime configuration and are excluded from Git.

Before starting the IN-CSE, open:

```text
in-cse-runtime\acme.ini
```

and replace:

```text
secret=CHANGE_ME
```

with a local secret value.

---

# Running the Prototype

The following instructions describe the local prototype setup using two ACME oneM2M CSE instances.

## 1. Start the IN-CSE

Open a PowerShell terminal in the project root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
acmecse -dir .\in-cse-runtime
```
The IN-CSE runs at:

```
http://127.0.0.1:8081

```

## 2. Start the MN-CSE

Open a second PowerShell terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
acmecse
```

The MN-CSE runs at:

```
http://127.0.0.1:8080

```

The MN-CSE registers with the IN-CSE through the oneM2M **Mcc** reference point.

## 3. Initial oneM2M Setup

For a fresh database, run:

```powershell
python src\onem2m_setup.py
python src\setup_acp.py
python src\setup_model_resource.py
```

These scripts create or verify the required oneM2M sensor resources, the Anomaly Detection AE, the alerts container, Access Control Policies, and the local model resource.

The setup scripts are idempotent and can safely be executed again. Existing correctly configured resources are reused instead of being duplicated.

## 4. Configure the Cloud Model Repository

Run:

```powershell
python src\setup_cloud_model_repo.py
python src\setup_cloud_repo_acp.py
```

These scripts initialize or verify the centralized model repository in the IN-CSE and configure its Access Control Policy.

They can safely be executed multiple times.

## 5. Train the Initial Model

If needed, train the initial model with:

```powershell
python src\train_model.py
```

This generates:

```
models/anomaly_model.joblib

```

The model is trained using simulated normal motor measurements.

## 6. Tune and Publish Model v2

With both CSE instances running, execute:

```powershell
python src\tune_model_v2.py
```

The script evaluates multiple One-Class SVM `nu` values using synthetic validation data.

It compares the false-positive rate on normal samples with the anomaly detection rate on simulated anomalous samples.

The selected model is saved locally and published to the IN-CSE model repository as version `v2`.

## 7. Deploy v2 to the Edge

Run:

```powershell
python src\deploy_model_v2_to_edge.py
```

The script:

- Retrieves model v2 through the MN-CSE using Mcc.
- Verifies the SHA-256 checksum.
- Saves the model locally.
- Publishes `version=v2, status=active` in the MN-CSE `/model` resource.

## 8. Start the Anomaly Detection Application

Open another PowerShell terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python src\notification_server.py
```

Expected startup output:

```
ELEKTRA - Anomaly Detection AE notification server
Sensor storage: oneM2M TimeSeries / TimeSeriesInstance
Model selection: active version from MN-CSE /model
Listening on http://127.0.0.1:9999/notify

```

With the notification server running, open another PowerShell terminal and create or verify the oneM2M subscription:

```powershell
python src\create_subscription.py
```

The subscription script is idempotent. If the correctly configured subscription already exists, it is reused.

The notification server receives oneM2M notifications, retrieves the latest sensor measurements, loads the active model, and performs inference.

## 9. Publish Simulated Motor Data

In another PowerShell terminal, run:

```powershell
python src\publish_sensor_data.py
```

Example output:

```
#01  T=65.62 C | V=0.335 | I=7.98 A  -> TimeSeries published (normal)
...
#05  ... -> TimeSeries published (ANOMALOUS TEST READING)

```

The notification server automatically performs inference when a notification is received.

Example output:

```
[MODEL] Loaded active model v2: anomaly_model_v2.joblib
[AI] ... | NORMAL | model=v2
[AI] ... | ANOMALY | model=v2
[ALERT] Saved automatically in oneM2M.

```

Detected anomalies are stored as oneM2M alert resources.

---

# ETSI MEC Sandbox

The current MEC integration uses an externally created MEC Application Instance.

The corresponding local scripts are:

```text
src/mec_confirm_ready.py
src/mec_discover_services.py
```

The MEC Sandbox session URL and Application Instance ID are not hard-coded in the repository because they can change between Sandbox sessions.

Before running the MEC scripts, configure the current Sandbox values as environment variables.

In PowerShell:

```powershell
$env:MEC_APP_SUPPORT_BASE="https://try-mec.etsi.org/<SANDBOX_ID>/mep1/mec_app_support/v2"
$env:MEC_SERVICE_MGMT_BASE="https://try-mec.etsi.org/<SANDBOX_ID>/mep1/mec_service_mgmt/v1"
$env:MEC_APP_INSTANCE_ID="<YOUR_APPLICATION_INSTANCE_ID>"
```

Replace `<SANDBOX_ID>` and `<YOUR_APPLICATION_INSTANCE_ID>` with the values provided by the current ETSI MEC Sandbox session.

Then run:

```powershell
python src\mec_confirm_ready.py
```

A successful readiness confirmation returns:

```text
HTTP 204
```

Service discovery can then be executed with:

```powershell
python src\mec_discover_services.py
```

A successful request returns:

```text
HTTP 200
```

together with the available MEC services.

The interaction flow is:

```text
Create MEC Application Instance
             |
             v
Configure MEC environment variables
             |
             v
mec_confirm_ready.py
             |
             v
HTTP 204
             |
             v
mec_discover_services.py
             |
             v
HTTP 200 + available services
```

The scripts demonstrate MEC application readiness confirmation and service discovery through the ETSI MEC APIs.

## Machine Learning

The anomaly detector uses the following pipeline:

```
StandardScaler
      |
      v
One-Class SVM

```

The training dataset contains simulated **normal** motor behaviour.

The tuned v2 model is selected by comparing different `nu` values using:

- False-positive rate on normal validation samples.
- Anomaly detection rate on synthetic anomalous validation samples.

In the current synthetic validation run, the selected v2 model achieved:

```
False-positive rate: approximately 2.38%
Anomaly detection rate: 100%

```

These results refer exclusively to the synthetic prototype dataset. They are not real-world industrial performance measurements and should not be interpreted as guarantees of detection accuracy in an actual industrial environment.

---

## Demo Flow

For a short live demonstration:

1. Start the IN-CSE.
2. Start the MN-CSE.
3. Start `notification_server.py`.
4. Run `publish_sensor_data.py`.
5. Show the `NORMAL` and `ANOMALY` inference outputs.
6. Show the generated alerts in the oneM2M resource tree.
7. Show the active model version (`v2`).
8. Optionally, run the MEC scripts to demonstrate MEC011 integration.

---

## Technologies

- Python
- oneM2M
- ACME oneM2M CSE
- ETSI MEC Sandbox
- scikit-learn
- One-Class SVM
- REST / HTTP
- oneM2M TimeSeries
- oneM2M Subscriptions
- oneM2M Access Control Policies
- oneM2M Mca / Mcc reference points

---

## Current Prototype Scope

### Implemented

- Simulated industrial sensor data.
- oneM2M TimeSeries resources.
- Event-driven subscriptions.
- Edge-side anomaly detection.
- Automatic anomaly alert storage.
- Access Control Policies.
- IN-CSE / MN-CSE architecture.
- Mcc communication.
- Centralized model repository.
- Model versioning.
- Cloud-to-edge model deployment.
- SHA-256 integrity verification.
- Dynamic active-model loading.
- ETSI MEC Sandbox application enablement.
- MEC service discovery.

### Not included

- Physical industrial sensors.
- Production-grade model training and validation.
- Real factory deployment.
- Production security credentials.
- Automated MEC orchestration.
- Verified execution of the ML inference process inside the MEC host.

---

## Disclaimer

This repository contains a research and hackathon prototype.

Sensor measurements and anomaly scenarios are simulated. The machine learning results are based on synthetic data and are intended to demonstrate the proposed architecture and workflow, not to provide production-grade industrial fault detection.

The project is not intended for safety-critical or production industrial use.
