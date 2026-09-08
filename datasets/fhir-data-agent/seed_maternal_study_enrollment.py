"""Enroll existing pregnant patients in the maternal-health ResearchStudy."""

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
STUDY_ID = "e7e8ae43-a33e-45c2-a0e3-be909d319ff9"
STUDY_REF = f"ResearchStudy/{STUDY_ID}"
GROUP_ID = "586f5f4c-9b36-496e-b0a9-380f5a121f4c"
ARM = "FHIR Coordinated Maternal Care"
ENROLL_DATE = "2026-09-07"
ENROLL_DT = "2026-09-07T12:00:00Z"

PATIENTS = [
    ("74ee3ce8-e896-433b-bb89-43c8ad5b333a", "Hedwig986 Will178"),
    ("9b553331-8f4a-43c1-b83f-55c6aa859de4", "Thalia561 Schimmel440"),
    ("ac2deca4-3467-4fa2-bf84-ae74289ef331", "Marisa391 Russel238"),
    ("d4a31e4f-2c79-4a7f-845b-519ef3c1f511", "Mahalia897 Hartmann983"),
    ("2bae212d-9da5-4b31-957f-86f058f84503", "Mekhi724 Kemmer911"),
    ("e81035c5-f3fa-42ad-88a0-b58a1ea6c994", "Julia241 Trantow673"),
    ("7a1c7fda-6b1a-44ff-b694-08ac926564c1", "Danuta945 Schmeler639"),
]


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
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def first_match(bundle, resource_type, predicate=None):
    if not isinstance(bundle, dict):
        return None
    for entry in bundle.get("entry") or []:
        resource = entry.get("resource") or {}
        if resource.get("resourceType") != resource_type:
            continue
        if predicate is None or predicate(resource):
            return resource
    return None


def consent_payload(pid: str, display: str) -> dict:
    return {
        "resourceType": "Consent",
        "status": "active",
        "scope": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/consentscope",
                    "code": "research",
                    "display": "Research",
                }
            ],
            "text": "Research",
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/consentcategorycodes",
                        "code": "research",
                        "display": "Research Study",
                    }
                ],
                "text": "Research study consent",
            }
        ],
        "patient": {"reference": f"Patient/{pid}", "display": display},
        "dateTime": ENROLL_DT,
        "policyRule": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "RESEARCH",
                    "display": "research",
                }
            ]
        },
        "provision": {
            "type": "permit",
            "period": {"start": ENROLL_DATE},
        },
    }


def subject_payload(pid: str, display: str, consent_id: str | None) -> dict:
    resource = {
        "resourceType": "ResearchSubject",
        "identifier": [
            {
                "use": "official",
                "system": "https://example.org/research/subjects",
                "value": f"MATERNAL-HEALTH-001-{pid[:8]}",
            }
        ],
        "status": "on-study",
        "period": {"start": ENROLL_DATE},
        "study": {
            "reference": STUDY_REF,
            "display": "Maternal Health Care Coordination Study",
        },
        "individual": {"reference": f"Patient/{pid}", "display": display},
        "assignedArm": ARM,
    }
    if consent_id:
        resource["consent"] = {"reference": f"Consent/{consent_id}"}
    return resource


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

    created = {"consent": {}, "subject": {}}
    for pid, display in PATIENTS:
        status, bundle = fhir(
            creds,
            "GET",
            f"/Consent?patient=Patient/{pid}&category=research&_count=5",
        )
        consent = first_match(
            bundle if status == 200 else {},
            "Consent",
            lambda r, pid=pid: r.get("status") == "active"
            and (r.get("patient") or {}).get("reference") == f"Patient/{pid}",
        )
        if consent:
            consent_id = consent["id"]
            print(" consent exists", pid, consent_id)
        else:
            payload = consent_payload(pid, display)
            post_status, body = fhir(creds, "POST", "/Consent", payload)
            if post_status not in (200, 201) or not isinstance(body, dict):
                # Retry without policyRule / provision if the store is strict.
                slim = {
                    k: payload[k]
                    for k in ("resourceType", "status", "scope", "category", "patient", "dateTime")
                }
                post_status, body = fhir(creds, "POST", "/Consent", slim)
            if post_status not in (200, 201) or not isinstance(body, dict):
                raise RuntimeError(f"Consent {pid} {post_status} {body}")
            consent_id = body["id"]
            print(" consent", pid, consent_id)
        created["consent"][pid] = consent_id

        status, bundle = fhir(
            creds,
            "GET",
            f"/ResearchSubject?study={STUDY_REF}&individual=Patient/{pid}&_count=5",
        )
        subject = first_match(
            bundle if status == 200 else {},
            "ResearchSubject",
            lambda r, pid=pid: (r.get("individual") or {}).get("reference")
            == f"Patient/{pid}",
        )
        payload = subject_payload(pid, display, consent_id)
        if subject:
            version = (subject.get("meta") or {}).get("versionId")
            payload["id"] = subject["id"]
            extra = {"If-Match": f'W/"{version}"'} if version else None
            put_status, body = fhir(
                creds, "PUT", f"/ResearchSubject/{subject['id']}", payload, extra
            )
        else:
            put_status, body = fhir(creds, "POST", "/ResearchSubject", payload)
        if put_status not in (200, 201) or not isinstance(body, dict):
            raise RuntimeError(f"ResearchSubject {pid} {put_status} {body}")
        print(" subject", pid, body["id"], body.get("status"))
        created["subject"][pid] = body["id"]
        time.sleep(0.1)

    group_status, group = fhir(creds, "GET", f"/Group/{GROUP_ID}")
    if group_status != 200 or not isinstance(group, dict):
        raise RuntimeError(f"Group GET {group_status} {group}")
    members = []
    for pid, display in PATIENTS:
        members.append(
            {
                "entity": {"reference": f"Patient/{pid}", "display": display},
                "period": {"start": ENROLL_DATE},
                "inactive": False,
            }
        )
    group["actual"] = True
    group["quantity"] = len(members)
    group["member"] = members
    version = (group.get("meta") or {}).get("versionId")
    extra = {"If-Match": f'W/"{version}"'} if version else None
    group.pop("meta", None)
    put_status, body = fhir(creds, "PUT", f"/Group/{GROUP_ID}", group, extra)
    if put_status not in (200, 201) or not isinstance(body, dict):
        raise RuntimeError(f"Group PUT {put_status} {body}")
    print("group", body.get("id"), "quantity", body.get("quantity"), "actual", body.get("actual"))

    print(json.dumps(created, indent=2))
    print("waiting for stream")
    time.sleep(18)
    bq = bigquery.Client(project=PROJECT, credentials=creds)
    tables = {
        row.table_name
        for row in bq.query(
            f"""
            SELECT table_name
            FROM `{PROJECT}.synth_healthcare.INFORMATION_SCHEMA.TABLES`
            WHERE table_name IN ('ResearchSubject', 'Consent', 'Group')
            """,
            job_config=bigquery.QueryJobConfig(labels={"datacloud": "cursor"}),
        ).result()
    }
    for table in ("ResearchSubject", "Consent", "Group"):
        if table in tables:
            print("collapse", table)
            collapse(bq, table)
        else:
            print("skip collapse, table not streamed yet", table)

    if "ResearchSubject" in tables:
        gap = list(
            bq.query(
                f"""
                WITH pregnant AS (
                  SELECT DISTINCT c.subject.patientId AS patient_id
                  FROM `{PROJECT}.synth_healthcare.Condition` c,
                       UNNEST(c.code.coding) coding
                  WHERE coding.code = '72892002'
                    AND c.clinicalStatus.coding[SAFE_OFFSET(0)].code = 'active'
                )
                SELECT COUNT(*) AS n
                FROM pregnant
                WHERE NOT EXISTS (
                  SELECT 1
                  FROM `{PROJECT}.synth_healthcare.ResearchSubject` rs
                  WHERE rs.status = 'on-study'
                    AND rs.study.researchStudyId = '{STUDY_ID}'
                    AND rs.individual.patientId = pregnant.patient_id
                )
                """,
                job_config=bigquery.QueryJobConfig(labels={"datacloud": "cursor"}),
            ).result()
        )
        print("pregnant missing on-study ResearchSubject", [dict(r) for r in gap])


if __name__ == "__main__":
    main()
