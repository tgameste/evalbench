"""Upsert the maternal-health study protocol and attach it to the study."""

from __future__ import annotations

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
PROTOCOL_ID = "maternal-health-study-protocol"
PROTOCOL_URL = (
    "https://example.org/fhir/PlanDefinition/maternal-health-study-protocol"
)
STUDY_ID = "e7e8ae43-a33e-45c2-a0e3-be909d319ff9"
STALE_PROTOCOL_ID = "9ae0e21e-89bc-4f38-8f45-0c97acc8d7c4"

PROTOCOL = {
    "resourceType": "PlanDefinition",
    "id": PROTOCOL_ID,
    "url": PROTOCOL_URL,
    "version": "1.0.0",
    "name": "MaternalHealthStudyProtocol",
    "title": "Maternal Health Care Coordination Study Protocol",
    "type": {"text": "Research study protocol"},
    "status": "active",
    "experimental": True,
    "date": "2026-09-07",
    "publisher": "Maternal Health Research Program",
    "description": (
        "Computable protocol for longitudinal maternal health care coordination "
        "using eight antenatal care contacts, assessments, questionnaires, "
        "laboratory testing, monitoring, patient engagement, and escalation workflows."
    ),
    "purpose": (
        "Define the computable workflow executed for participants enrolled in "
        "the Maternal Health Care Coordination Study."
    ),
    "usage": (
        "Applied after a participant has consented and a ResearchSubject has "
        "entered on-study status."
    ),
    "subjectCodeableConcept": {
        "coding": [
            {
                "system": "http://hl7.org/fhir/resource-types",
                "code": "Patient",
                "display": "Patient",
            }
        ],
        "text": "Pregnant patient",
    },
    "relatedArtifact": [
        {
            "type": "derived-from",
            "display": "WHO ANC8 PlanDefinition",
            "resource": "https://langcare.example.org/fhir/PlanDefinition/who-anc8",
        }
    ],
    "action": [
        {
            "id": "anc-contact-1",
            "prefix": "1",
            "title": "ANC Contact 1",
            "description": "Initial antenatal assessment at 0-12 weeks gestation.",
            "textEquivalent": (
                "Perform initial history, physical examination, risk assessment, "
                "baseline laboratory evaluation, patient education, and early "
                "pregnancy care activities."
            ),
            "priority": "routine",
            "timingTiming": {
                "repeat": {"boundsPeriod": {"start": "2026-09-07"}}
            },
            "action": [
                {
                    "id": "anc1-history",
                    "title": "Clinical history and risk assessment",
                    "description": (
                        "Collect obstetric, medical, medication, social, and "
                        "behavioral health history."
                    ),
                },
                {
                    "id": "anc1-vitals",
                    "title": "Baseline maternal observations",
                    "description": (
                        "Capture blood pressure, weight, height, BMI, and other "
                        "baseline maternal observations."
                    ),
                },
                {
                    "id": "anc1-labs",
                    "title": "Baseline laboratory investigations",
                    "description": (
                        "Perform pregnancy-appropriate baseline laboratory investigations."
                    ),
                },
                {
                    "id": "anc1-questionnaire",
                    "title": "Maternal health questionnaire",
                    "description": (
                        "Collect structured patient-reported maternal health and "
                        "risk information."
                    ),
                },
            ],
        },
        {
            "id": "anc-contact-2",
            "prefix": "2",
            "title": "ANC Contact 2",
            "description": "Antenatal contact approximately 20 weeks gestation.",
            "action": [
                {"title": "Maternal assessment"},
                {"title": "Fetal assessment"},
                {"title": "Ultrasound review"},
                {"title": "Patient education"},
            ],
        },
        {
            "id": "anc-contact-3",
            "prefix": "3",
            "title": "ANC Contact 3",
            "description": "Antenatal contact approximately 26 weeks gestation.",
            "action": [
                {"title": "Maternal assessment"},
                {"title": "Blood pressure and weight monitoring"},
                {"title": "Laboratory and screening review"},
            ],
        },
        {
            "id": "anc-contact-4",
            "prefix": "4",
            "title": "ANC Contact 4",
            "description": "Antenatal contact approximately 30 weeks gestation.",
            "action": [
                {"title": "Maternal assessment"},
                {"title": "Fetal assessment"},
                {"title": "Risk classification review"},
            ],
        },
        {
            "id": "anc-contact-5",
            "prefix": "5",
            "title": "ANC Contact 5",
            "description": "Antenatal contact approximately 34 weeks gestation.",
            "action": [
                {"title": "Maternal assessment"},
                {"title": "Preeclampsia risk surveillance"},
                {"title": "Birth preparedness assessment"},
            ],
        },
        {
            "id": "anc-contact-6",
            "prefix": "6",
            "title": "ANC Contact 6",
            "description": "Antenatal contact approximately 36 weeks gestation.",
            "action": [
                {"title": "Maternal assessment"},
                {"title": "Fetal assessment"},
                {"title": "Delivery readiness"},
            ],
        },
        {
            "id": "anc-contact-7",
            "prefix": "7",
            "title": "ANC Contact 7",
            "description": "Antenatal contact approximately 38 weeks gestation.",
            "action": [
                {"title": "Maternal assessment"},
                {"title": "Fetal wellbeing assessment"},
                {"title": "Risk reassessment"},
            ],
        },
        {
            "id": "anc-contact-8",
            "prefix": "8",
            "title": "ANC Contact 8",
            "description": "Antenatal contact approximately 40 weeks gestation.",
            "action": [
                {"title": "Maternal assessment"},
                {"title": "Fetal assessment"},
                {"title": "Delivery planning"},
            ],
        },
        {
            "id": "continuous-monitoring",
            "title": "Continuous Maternal Risk Monitoring",
            "description": (
                "Continuously evaluate available maternal observations, laboratory "
                "results, symptoms, questionnaire responses, and remote patient "
                "monitoring data for changes in maternal risk."
            ),
        },
        {
            "id": "escalation",
            "title": "Maternal Risk Escalation",
            "description": (
                "Initiate provider review when clinically significant maternal "
                "risk evidence is detected."
            ),
            "priority": "urgent",
            "condition": [
                {
                    "kind": "applicability",
                    "expression": {
                        "language": "text/fhirpath",
                        "expression": "%maternalRiskDetected",
                    },
                }
            ],
        },
    ],
}


def fhir(creds, method, path, body=None, extra=None):
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
        return exc.code, json.loads(exc.read().decode() or "{}")


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

    status, existing = fhir(creds, "GET", f"/PlanDefinition/{PROTOCOL_ID}")
    extra = None
    target_id = PROTOCOL_ID
    if status == 200 and isinstance(existing, dict) and existing.get("id"):
        target_id = existing["id"]
        version = (existing.get("meta") or {}).get("versionId")
        extra = {"If-Match": f'W/"{version}"'} if version else None
        payload = {**PROTOCOL, "id": target_id}
        put_status, body = fhir(
            creds, "PUT", f"/PlanDefinition/{target_id}", payload, extra
        )
    else:
        payload = {**PROTOCOL, "id": PROTOCOL_ID}
        put_status, body = fhir(
            creds, "POST", "/PlanDefinition", payload
        )
        if put_status in (400, 404, 405, 409, 422):
            stale_status, stale = fhir(
                creds, "GET", f"/PlanDefinition/{STALE_PROTOCOL_ID}"
            )
            if stale_status == 200 and isinstance(stale, dict) and stale.get("id"):
                target_id = stale["id"]
                version = (stale.get("meta") or {}).get("versionId")
                extra = {"If-Match": f'W/"{version}"'} if version else None
                payload = {**PROTOCOL, "id": target_id}
                put_status, body = fhir(
                    creds, "PUT", f"/PlanDefinition/{target_id}", payload, extra
                )
    if put_status not in (200, 201) or not isinstance(body, dict):
        raise RuntimeError(f"PlanDefinition upsert {put_status} {body}")
    target_id = body["id"]
    print("protocol", target_id, put_status)

    study_status, study = fhir(creds, "GET", f"/ResearchStudy/{STUDY_ID}")
    if study_status != 200 or not isinstance(study, dict):
        raise RuntimeError(f"ResearchStudy GET {study_status} {study}")
    study["protocol"] = [
        {
            "reference": f"PlanDefinition/{target_id}",
            "display": PROTOCOL["title"],
        }
    ]
    version = (study.get("meta") or {}).get("versionId")
    extra = {"If-Match": f'W/"{version}"'} if version else None
    study.pop("meta", None)
    put_status, body = fhir(
        creds, "PUT", f"/ResearchStudy/{STUDY_ID}", study, extra
    )
    if put_status not in (200, 201) or not isinstance(body, dict):
        raise RuntimeError(f"ResearchStudy PUT {put_status} {body}")
    print("study protocol", body.get("id"), [p.get("reference") for p in body.get("protocol") or []])

    print("waiting for stream")
    time.sleep(16)
    bq = bigquery.Client(project=PROJECT, credentials=creds)
    for table in ("PlanDefinition", "ResearchStudy"):
        print("collapse", table)
        collapse(bq, table)


if __name__ == "__main__":
    main()
