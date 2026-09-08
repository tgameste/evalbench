"""Apply two WHO ANC8 ActivityDefinitions onto one CPG CarePlan.

Healthcare API demo-r4 has no $apply. This script is the apply engine for a
single patient-independent slice:

- ActivityDefinition/practice-blood-pressure → ServiceRequest intent=proposal
- ActivityDefinition/practice-warning-signs → CommunicationRequest (R4 has no intent)

Both requests basedOn CarePlan/e7b5bdec-… (Hedwig). The CarePlan hangs them
as activity.reference only (cpl-3: no inline detail on those activities).
Existing Patient-action details are left untouched.
"""

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
PATIENT_ID = "74ee3ce8-e896-433b-bb89-43c8ad5b333a"
CAREPLAN_ID = "e7b5bdec-76e5-4d97-9725-a43c29978af1"
CONDITION_ID = "39506ae8-daad-4afe-9f68-d772d53acd33"
SNOMED = "http://snomed.info/sct"
AD_BASE = "https://langcare.example.org/fhir/ActivityDefinition"
BP_AD = f"{AD_BASE}/practice-blood-pressure"
EDU_AD = f"{AD_BASE}/practice-warning-signs"
EDU_URL = "https://www.cdc.gov/hearher/maternal-warning-signs/index.html"
CAREPLAN_TITLE = "WHO ANC8 antenatal pathway"
INSTANTIATES_EXT = (
    "http://hl7.org/fhir/StructureDefinition/workflow-instantiatesCanonical"
)


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


def strip_meta(resource: dict) -> dict:
    meta = resource.get("meta") or {}
    kept = {k: v for k, v in meta.items() if k in ("profile",)}
    if kept:
        resource["meta"] = kept
    else:
        resource.pop("meta", None)
    return resource


def coding(code: str, display: str) -> dict:
    return {"system": SNOMED, "code": code, "display": display}


def collapse(bq, table: str) -> None:
    bq.query(
        f"""
        CREATE OR REPLACE TABLE `{PROJECT}.synth_healthcare.{table}` AS
        SELECT * FROM `{PROJECT}.synth_healthcare.{table}`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY commitTimestamp DESC) = 1
        """,
        job_config=bigquery.QueryJobConfig(labels={"datacloud": "cursor"}),
    ).result()


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

    def search_patient(resource_type: str):
        status, bundle = fhir(
            "GET",
            f"/{resource_type}?patient=Patient/{PATIENT_ID}&_count=50",
        )
        if status != 200 or not isinstance(bundle, dict):
            return []
        return [
            entry.get("resource") or {}
            for entry in (bundle.get("entry") or [])
            if (entry.get("resource") or {}).get("resourceType") == resource_type
        ]

    def instantiates_of(resource: dict) -> set[str]:
        found = set(resource.get("instantiatesCanonical") or [])
        for ident in resource.get("identifier") or []:
            if ident.get("system") == AD_BASE and ident.get("value"):
                found.add(f"{AD_BASE}/{ident['value']}")
        for ext in resource.get("extension") or []:
            if ext.get("url") == INSTANTIATES_EXT and ext.get("valueCanonical"):
                found.add(ext["valueCanonical"])
        return found

    def upsert_service_request() -> str:
        for existing in search_patient("ServiceRequest"):
            if BP_AD in instantiates_of(existing):
                print("  reuse ServiceRequest", existing["id"])
                return existing["id"]
        payload = {
            "resourceType": "ServiceRequest",
            "status": "active",
            "intent": "proposal",
            "priority": "routine",
            "instantiatesCanonical": [BP_AD],
            "basedOn": [{"reference": f"CarePlan/{CAREPLAN_ID}"}],
            "code": {
                "coding": [coding("75367002", "Blood pressure taking (procedure)")],
                "text": "Blood pressure taking (procedure)",
            },
            "subject": {"reference": f"Patient/{PATIENT_ID}"},
            "authoredOn": "2026-09-07",
            "reasonReference": [{"reference": f"Condition/{CONDITION_ID}"}],
            "bodySite": [
                {
                    "coding": [coding("368209003", "Right upper arm structure")],
                    "text": "Right upper arm structure",
                }
            ],
        }
        status, body = fhir("POST", "/ServiceRequest", payload)
        if status not in (200, 201) or not isinstance(body, dict):
            raise RuntimeError(f"ServiceRequest POST {status} {body}")
        print("  new ServiceRequest", body["id"])
        return body["id"]

    def upsert_communication_request() -> str:
        for existing in search_patient("CommunicationRequest"):
            if EDU_AD in instantiates_of(existing):
                print("  reuse CommunicationRequest", existing["id"])
                return existing["id"]
        payload = {
            "resourceType": "CommunicationRequest",
            "status": "active",
            "priority": "routine",
            "identifier": [
                {
                    "use": "official",
                    "system": AD_BASE,
                    "value": "practice-warning-signs",
                }
            ],
            "extension": [
                {"url": INSTANTIATES_EXT, "valueCanonical": EDU_AD},
            ],
            "basedOn": [{"reference": f"CarePlan/{CAREPLAN_ID}"}],
            "category": [
                {
                    "coding": [coding("311401005", "Patient education (procedure)")],
                    "text": "Patient education (procedure)",
                }
            ],
            "subject": {"reference": f"Patient/{PATIENT_ID}"},
            "payload": [
                {
                    "contentString": (
                        "Review HEAR HER maternal warning signs: " + EDU_URL
                    )
                }
            ],
            "authoredOn": "2026-09-07",
            "reasonReference": [{"reference": f"Condition/{CONDITION_ID}"}],
        }
        status, body = fhir("POST", "/CommunicationRequest", payload)
        if status not in (200, 201) or not isinstance(body, dict):
            raise RuntimeError(f"CommunicationRequest POST {status} {body}")
        print("  new CommunicationRequest", body["id"])
        return body["id"]

    sr_id = retry(upsert_service_request)
    cr_id = retry(upsert_communication_request)

    def update_careplan():
        status, resource = fhir("GET", f"/CarePlan/{CAREPLAN_ID}")
        if status != 200 or not isinstance(resource, dict):
            raise RuntimeError(f"CarePlan GET {status} {resource}")
        version = (resource.get("meta") or {}).get("versionId")
        updated = strip_meta(copy.deepcopy(resource))
        updated["status"] = "active"
        updated["intent"] = updated.get("intent") or "order"
        updated["title"] = CAREPLAN_TITLE
        updated["subject"] = {"reference": f"Patient/{PATIENT_ID}"}
        activities = copy.deepcopy(updated.get("activity") or [])
        wanted = {
            f"ServiceRequest/{sr_id}",
            f"CommunicationRequest/{cr_id}",
        }
        have = {
            (act.get("reference") or {}).get("reference")
            for act in activities
            if (act.get("reference") or {}).get("reference")
        }
        for ref in sorted(wanted - have):
            activities.append({"reference": {"reference": ref}})
        updated["activity"] = activities
        extra = {"If-Match": f'W/"{version}"'} if version else None
        put_status, put_body = fhir(
            "PUT", f"/CarePlan/{CAREPLAN_ID}", updated, extra=extra
        )
        if put_status not in (200, 201) or not isinstance(put_body, dict):
            raise RuntimeError(f"CarePlan PUT {put_status} {put_body}")
        return {
            "careplan": put_body["id"],
            "service_request": sr_id,
            "communication_request": cr_id,
            "activity_n": len(put_body.get("activity") or []),
        }

    result = retry(update_careplan)
    print(json.dumps(result, indent=2))
    print("waiting for stream")
    time.sleep(18)

    bq = bigquery.Client(project=PROJECT, credentials=creds)
    for table in ("CarePlan", "ServiceRequest"):
        print("collapse", table)
        collapse(bq, table)
    tables = {
        row.table_id
        for row in bq.list_tables(f"{PROJECT}.synth_healthcare")
    }
    if "CommunicationRequest" in tables:
        print("collapse CommunicationRequest")
        collapse(bq, "CommunicationRequest")
    else:
        print("CommunicationRequest not streamed yet")

    check = list(
        bq.query(
            f"""
            SELECT
              (SELECT COUNT(*)
               FROM `{PROJECT}.synth_healthcare.ServiceRequest` sr,
                    UNNEST(sr.instantiatesCanonical) inst
               WHERE sr.subject.patientId = '{PATIENT_ID}'
                 AND sr.intent = 'proposal'
                 AND inst = '{BP_AD}') AS bp_proposals,
              (SELECT COUNT(*)
               FROM `{PROJECT}.synth_healthcare.CarePlan` cp,
                    UNNEST(cp.activity) act
               WHERE cp.id = '{CAREPLAN_ID}'
                 AND act.reference.serviceRequestId IS NOT NULL) AS cp_sr_refs
            """,
            job_config=bigquery.QueryJobConfig(labels={"datacloud": "cursor"}),
        ).result()
    )
    print("bq snapshot", [dict(r) for r in check])


if __name__ == "__main__":
    main()
