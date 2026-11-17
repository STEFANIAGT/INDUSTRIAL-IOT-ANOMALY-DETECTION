import uuid
import requests

IN_BASE = "http://127.0.0.1:8081/cse-in"
ADMIN = "CAdmin"
REMOTE_MN_ADMIN = "/id-mn/CAdmin"


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


def get(path, originator=ADMIN):
    return requests.get(
        f"{IN_BASE}/{path}",
        headers=headers(originator),
        timeout=5,
    )


def get_model_manager_originator():
    r = get("ModelManagerAE", ADMIN)
    if r.status_code != 200:
        print(f"[ERROR] Cannot retrieve ModelManagerAE: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    ae = r.json()["m2m:ae"]
    return ae.get("aei", "CModelManagerAE")


def create_or_update_acp(model_manager_originator):
    rn = "cloudModelRepoACP"

    privileges = [
        {"acor": [model_manager_originator], "acop": 63},
        {"acor": [REMOTE_MN_ADMIN], "acop": 2},  # RETRIEVE only
        {"acor": [ADMIN], "acop": 63},
    ]

    self_privileges = [
        {"acor": [model_manager_originator], "acop": 63},
        {"acor": [ADMIN], "acop": 63},
    ]

    body = {
        "m2m:acp": {
            "pv": {"acr": privileges},
            "pvs": {"acr": self_privileges},
        }
    }

    existing = get(rn, ADMIN)

    if existing.status_code == 200:
        r = requests.put(
            f"{IN_BASE}/{rn}",
            headers=headers(ADMIN),
            json=body,
            timeout=5,
        )
        if r.status_code == 200:
            print("[OK] Updated cloudModelRepoACP.")
            return r.json()["m2m:acp"]["ri"]

        print(f"[ERROR] Cannot update cloudModelRepoACP: HTTP {r.status_code}")
        print(r.text)
        raise SystemExit(1)

    create_body = {
        "m2m:acp": {
            "rn": rn,
            "pv": {"acr": privileges},
            "pvs": {"acr": self_privileges},
        }
    }

    r = requests.post(
        IN_BASE,
        headers=headers(ADMIN, 1),
        json=create_body,
        timeout=5,
    )

    if r.status_code in (200, 201):
        print("[OK] Created cloudModelRepoACP.")
        return r.json()["m2m:acp"]["ri"]

    print(f"[ERROR] Cannot create cloudModelRepoACP: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def assign_acp(path, acp_ri, originator):
    body = {
        "m2m:cnt": {
            "acpi": [acp_ri]
        }
    }

    r = requests.put(
        f"{IN_BASE}/{path}",
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


def verify_remote_permission_directly():
    r = get(
        "ModelManagerAE/modelRepo/anomalyModel/v1",
        REMOTE_MN_ADMIN,
    )

    if r.status_code == 200:
        print("[OK] /id-mn/CAdmin has RETRIEVE permission on model v1.")
        return

    print(f"[ERROR] Permission verification failed: HTTP {r.status_code}")
    print(r.text)
    raise SystemExit(1)


def main():
    print("Configuring cloud model repository ACP...")
    print()

    model_manager_originator = get_model_manager_originator()
    print(f"[INFO] ModelManagerAE originator: {model_manager_originator}")

    acp_ri = create_or_update_acp(model_manager_originator)

    # The model version is a ContentInstance below anomalyModel.
    # Protect the parent container; the instance uses the parent's access policy.
    assign_acp(
        "ModelManagerAE/modelRepo/anomalyModel",
        acp_ri,
        model_manager_originator,
    )

    print()
    verify_remote_permission_directly()

    print()
    print("DONE. Cloud model repository is readable from MN-CSE with RETRIEVE-only access.")


if __name__ == "__main__":
    main()
