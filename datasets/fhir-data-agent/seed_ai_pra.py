"""Ensure WHO ANC8 + AI pregnancy-risk assessments have adequate grounded inputs."""

from __future__ import annotations

import copy
import json
import time
import urllib.error
import urllib.request

from google.auth import default
from google.auth.transport.requests import Request
from google.cloud import bigquery

PROJECT = "mktg-vdc-poc-r83n"
FHIR_BASE = (
    "https://healthcare.googleapis.com/v1/"
    f"projects/{PROJECT}/locations/us-west2/datasets/langcare-demo/"
    "fhirStores/demo-r4/fhir"
)
ID_SYSTEM = "https://langcare.example.org/fhir/sid/risk-evidence"
WHO_FULL = "https://langcare.example.org/fhir/PlanDefinition/who-anc8"
WHO_SHORT = "PlanDefinition/who-anc8"
AI_METHOD = {
    "coding": [
        {
            "system": "https://langcare.health/fhir/assessment-method",
            "code": "pregnancy_risk_assessment",
            "display": "LangCare pregnancy_risk_assessment",
        }
    ],
    "text": "LangCare pregnancy_risk_assessment",
}

PATIENTS = [
    {
        "pid": "74ee3ce8-e896-433b-bb89-43c8ad5b333a",
        "cp": "e7b5bdec-76e5-4d97-9725-a43c29978af1",
        "ra": "e5e4c8da-143e-4675-8d40-04e235a84052",
        "ga_weeks": 28,
        "need": ["11881-0"],
    },
    {
        "pid": "9b553331-8f4a-43c1-b83f-55c6aa859de4",
        "cp": "386a9ae4-700d-4bbb-92d2-608e3e3e70ae",
        "ra": "1d507bc4-b7ce-4039-81bf-2c8fd2db2ed0",
        "ga_weeks": 22,
        "need": ["11881-0"],
    },
    {
        "pid": "ac2deca4-3467-4fa2-bf84-ae74289ef331",
        "cp": "d81645b6-8354-4cd5-9e4b-2fa552d910f7",
        "ra": "e71e4d4b-fc0d-4211-98a4-55ab3516076a",
        "ga_weeks": 30,
        "need": ["11881-0"],
    },
    {
        "pid": "d4a31e4f-2c79-4a7f-845b-519ef3c1f511",
        "cp": "aaa5d20e-41f7-498f-a509-f264d0878b2e",
        "ra": "9c89eb86-6931-4219-8c2b-95260fe1387e",
        "ga_weeks": 26,
        "need": ["11881-0"],
    },
    {
        "pid": "2bae212d-9da5-4b31-957f-86f058f84503",
        "cp": "4612770b-5197-4578-a07a-9f2674cc66e3",
        "ra": "975a1f0e-3ae5-4a0f-af17-daecdb29dd7e",
        "ga_weeks": 20,
        "need": ["11881-0", "82810-3", "2345-7", "72166-2"],
    },
    {
        "pid": "e81035c5-f3fa-42ad-88a0-b58a1ea6c994",
        "cp": "c60df24d-6422-46b9-bad5-7f6fac9cc00b",
        "ra": "5fb3ac84-af62-4f03-80d0-94ac4c7f839f",
        "ga_weeks": 24,
        "need": ["11881-0"],
    },
    {
        "pid": "7a1c7fda-6b1a-44ff-b694-08ac926564c1",
        "cp": "35dec952-71ca-48f4-87a3-a895221a28ef",
        "ra": "b9477cd4-69de-4e92-83a6-4483fcc7b382",
        "ga_weeks": 18,
        "need": ["11881-0"],
    },
]


def retry(fn, attempts=5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            print(f"  retry {i + 1}: {exc}")
            time.sleep(1.2 * (i + 1))
    raise last


def main() -> None:
    creds, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())

    def fhir(method, path, body=None, extra=None):
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Accept": "application/fhir+json",
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/fhir+json"
            data = json.dumps(body).encode()
        if extra:
            headers.update(extra)
        req = urllib.request.Request(
            FHIR_BASE + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def strip_meta(resource):
        meta = resource.get("meta") or {}
        kept = {k: v for k, v in meta.items() if k in ("profile",)}
        if kept:
            resource["meta"] = kept
        else:
            resource.pop("meta", None)
        return resource

    def find_by_identifier(resource_type, value):
        status, bundle = fhir(
            "GET",
            f"/{resource_type}?identifier={ID_SYSTEM}|{value}&_count=5",
        )
        if status == 200 and isinstance(bundle, dict):
            for entry in bundle.get("entry") or []:
                resource = entry.get("resource") or {}
                if resource.get("id"):
                    return resource
        return None

    def upsert_observation(ident, body):
        existing = find_by_identifier("Observation", ident)
        if existing:
            version = existing["meta"]["versionId"]
            updated = strip_meta(copy.deepcopy(existing))
            updated.update(body)
            updated["id"] = existing["id"]
            status, resp = fhir(
                "PUT",
                f"/Observation/{existing['id']}",
                updated,
                extra={"If-Match": f'W/"{version}"'},
            )
            if status not in (200, 201) or not isinstance(resp, dict):
                raise RuntimeError(f"Observation PUT {status} {resp}")
            return resp["id"]
        status, resp = fhir("POST", "/Observation", body)
        if status not in (200, 201) or not isinstance(resp, dict):
            raise RuntimeError(f"Observation POST {status} {resp}")
        return resp["id"]

    def pra_obs(pid, loinc, display, value_field):
        ident = f"pra|{loinc}|{pid}"
        body = {
            "resourceType": "Observation",
            "status": "final",
            "identifier": [{"system": ID_SYSTEM, "value": ident}],
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "exam",
                            "display": "Exam",
                        }
                    ],
                    "text": "pra-input",
                }
            ],
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": loinc,
                        "display": display,
                    }
                ],
                "text": "Pregnancy risk assessment input",
            },
            "subject": {"reference": f"Patient/{pid}"},
            "effectiveDateTime": "2026-06-15T00:00:00Z",
        }
        body.update(value_field)
        return upsert_observation(ident, body)

    def ensure_device():
        existing = find_by_identifier("Device", "ai-pra-agent")
        if existing:
            return existing["id"]
        body = {
            "resourceType": "Device",
            "identifier": [{"system": ID_SYSTEM, "value": "ai-pra-agent"}],
            "status": "active",
            "type": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "706689003",
                        "display": "Application program software",
                    }
                ],
                "text": "AI pregnancy risk assessment agent",
            },
            "deviceName": [
                {
                    "name": "LangCare pregnancy_risk_assessment",
                    "type": "user-friendly-name",
                }
            ],
        }
        status, resp = fhir("POST", "/Device", body)
        if status not in (200, 201) or not isinstance(resp, dict):
            raise RuntimeError(f"Device POST {status} {resp}")
        return resp["id"]

    device_id = retry(ensure_device)
    print("device", device_id)

    created = {}
    for row in PATIENTS:
        pid = row["pid"]
        print("==", pid)
        obs_ids = {}
        for loinc in row["need"]:
            if loinc == "11881-0":

                def make_ga(row=row, pid=pid):
                    return pra_obs(
                        pid,
                        "11881-0",
                        "Gestational age Estimated from last menstrual period",
                        {
                            "valueQuantity": {
                                "value": row["ga_weeks"],
                                "unit": "wk",
                                "system": "http://unitsofmeasure.org",
                                "code": "wk",
                            }
                        },
                    )

                obs_ids[loinc] = retry(make_ga)
            elif loinc == "82810-3":

                def make_preg(pid=pid):
                    return pra_obs(
                        pid,
                        "82810-3",
                        "Pregnancy status",
                        {
                            "valueCodeableConcept": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "LA15173-0",
                                        "display": "Pregnant",
                                    }
                                ],
                                "text": "Pregnant",
                            }
                        },
                    )

                obs_ids[loinc] = retry(make_preg)
            elif loinc == "2345-7":

                def make_glu(pid=pid):
                    return pra_obs(
                        pid,
                        "2345-7",
                        "Glucose [Mass/volume] in Serum or Plasma",
                        {
                            "valueQuantity": {
                                "value": 82,
                                "unit": "mg/dL",
                                "system": "http://unitsofmeasure.org",
                                "code": "mg/dL",
                            },
                            "interpretation": [
                                {
                                    "coding": [
                                        {
                                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                                            "code": "N",
                                            "display": "Normal",
                                        }
                                    ]
                                }
                            ],
                        },
                    )

                obs_ids[loinc] = retry(make_glu)
            elif loinc == "72166-2":

                def make_smoke(pid=pid):
                    return pra_obs(
                        pid,
                        "72166-2",
                        "Tobacco smoking status",
                        {
                            "valueCodeableConcept": {
                                "coding": [
                                    {
                                        "system": "http://snomed.info/sct",
                                        "code": "266919005",
                                        "display": "Never smoked tobacco",
                                    }
                                ],
                                "text": "Never smoker",
                            }
                        },
                    )

                obs_ids[loinc] = retry(make_smoke)
            print(" ", loinc, obs_ids.get(loinc))

        def update_cp(row=row):
            status, resource = fhir("GET", f"/CarePlan/{row['cp']}")
            if status != 200 or not isinstance(resource, dict):
                raise RuntimeError(f"CarePlan GET {status} {resource}")
            version = resource["meta"]["versionId"]
            updated = strip_meta(copy.deepcopy(resource))
            updated["status"] = "active"
            canons = list(updated.get("instantiatesCanonical") or [])
            if WHO_FULL not in canons:
                canons.insert(0, WHO_FULL)
            if WHO_SHORT not in canons:
                canons.append(WHO_SHORT)
            updated["instantiatesCanonical"] = canons
            put_status, put_body = fhir(
                "PUT",
                f"/CarePlan/{row['cp']}",
                updated,
                extra={"If-Match": f'W/"{version}"'},
            )
            if put_status not in (200, 201) or not isinstance(put_body, dict):
                raise RuntimeError(f"CarePlan PUT {put_status} {put_body}")
            return row["cp"]

        def update_ra(row=row, device_id=device_id):
            status, resource = fhir("GET", f"/RiskAssessment/{row['ra']}")
            if status != 200 or not isinstance(resource, dict):
                raise RuntimeError(f"RiskAssessment GET {status} {resource}")
            version = resource["meta"]["versionId"]
            updated = strip_meta(copy.deepcopy(resource))
            updated["method"] = AI_METHOD
            updated["basedOn"] = {"reference": f"CarePlan/{row['cp']}"}
            updated["performer"] = {"reference": f"Device/{device_id}"}
            put_status, put_body = fhir(
                "PUT",
                f"/RiskAssessment/{row['ra']}",
                updated,
                extra={"If-Match": f'W/"{version}"'},
            )
            if put_status not in (200, 201) or not isinstance(put_body, dict):
                raise RuntimeError(f"RiskAssessment PUT {put_status} {put_body}")
            return row["ra"]

        print("  careplan", retry(update_cp), "ra", retry(update_ra))
        created[pid] = {"obs": obs_ids, "device": device_id}

    print(json.dumps(created, indent=2))
    print("waiting for stream")
    time.sleep(16)
    bq = bigquery.Client(project=PROJECT, credentials=creds)
    for table in ("Observation", "CarePlan", "RiskAssessment", "Device"):
        print("collapse", table)
        bq.query(
            f"""
        CREATE OR REPLACE TABLE `{PROJECT}.synth_healthcare.{table}` AS
        SELECT * FROM `{PROJECT}.synth_healthcare.{table}`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY commitTimestamp DESC) = 1
        """
        ).result()


if __name__ == "__main__":
    main()
