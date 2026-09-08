"""Seed maternal/neonatal goals, education URLs, and completed access Tasks."""

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
WHO_FULL = "https://langcare.example.org/fhir/PlanDefinition/who-anc8"
WHO_SHORT = "PlanDefinition/who-anc8"
WHO_DESC = (
    "Routine antenatal care pathway updated to align with the WHO 8-contact model guidelines."
)
GOAL_MATERNAL = "Maternal Health Mortality Reduction"
GOAL_NEONATAL = "Neonatal / Fetal Co-morbidity Reduction"
NEONATAL_URL = "https://www.cdc.gov/maternal-infant-health/infant-health/index.html"

PATIENTS = [
    {
        "pid": "74ee3ce8-e896-433b-bb89-43c8ad5b333a",
        "cp": "e7b5bdec-76e5-4d97-9725-a43c29978af1",
        "cond": "39506ae8-daad-4afe-9f68-d772d53acd33",
        "risk": "Moderate",
        "specific": "59621000",
        "has_ra": True,
        "ra": "e5e4c8da-143e-4675-8d40-04e235a84052",
    },
    {
        "pid": "9b553331-8f4a-43c1-b83f-55c6aa859de4",
        "cp": "386a9ae4-700d-4bbb-92d2-608e3e3e70ae",
        "cond": "650d96fc-9ee4-4019-9c6d-648e225681b5",
        "risk": "Low",
        "specific": "72892002",
        "has_ra": True,
        "ra": "1d507bc4-b7ce-4039-81bf-2c8fd2db2ed0",
    },
    {
        "pid": "ac2deca4-3467-4fa2-bf84-ae74289ef331",
        "cp": "d81645b6-8354-4cd5-9e4b-2fa552d910f7",
        "cond": "531a95c1-89d9-4a67-955c-d9a0a7a126b0",
        "risk": "High",
        "specific": "72892002",
        "has_ra": True,
        "ra": "e71e4d4b-fc0d-4211-98a4-55ab3516076a",
    },
    {
        "pid": "d4a31e4f-2c79-4a7f-845b-519ef3c1f511",
        "cp": "aaa5d20e-41f7-498f-a509-f264d0878b2e",
        "cond": "4dbd1161-9806-43a0-9aa5-2db5f9591b6e",
        "risk": "Moderate",
        "specific": "72892002",
        "has_ra": True,
        "ra": "9c89eb86-6931-4219-8c2b-95260fe1387e",
    },
    {
        "pid": "2bae212d-9da5-4b31-957f-86f058f84503",
        "cp": "4612770b-5197-4578-a07a-9f2674cc66e3",
        "cond": "9dacfb25-78f1-4ffc-a084-ce02d2092b24",
        "risk": "Low",
        "specific": "72892002",
        "has_ra": True,
        "ra": "975a1f0e-3ae5-4a0f-af17-daecdb29dd7e",
    },
    {
        "pid": "e81035c5-f3fa-42ad-88a0-b58a1ea6c994",
        "cp": "c60df24d-6422-46b9-bad5-7f6fac9cc00b",
        "cond": "67a33a30-7e95-46de-997b-08334edb66dc",
        "risk": "Low",
        "specific": "72892002",
        "has_ra": True,
        "ra": "5fb3ac84-af62-4f03-80d0-94ac4c7f839f",
    },
    {
        "pid": "7a1c7fda-6b1a-44ff-b694-08ac926564c1",
        "cp": "35dec952-71ca-48f4-87a3-a895221a28ef",
        "cond": "4db28a4e-81e1-4588-a4e8-79195b11c4e5",
        "risk": "Low",
        "specific": "72892002",
        "has_ra": True,
        "ra": "b9477cd4-69de-4e92-83a6-4483fcc7b382",
    },
]


def education_url(risk: str, specific: str) -> str:
    """Golden maternal education URL for pregnancy risk + specific condition.

    Low + SNOMED 72892002 → CDC pregnancy-during
    Moderate or HTN 59621000 → CDC HEAR HER warning signs
    High → CDC HEAR HER hub
    Neonatal URL is always NEONATAL_URL.
    """
    if specific == "59621000" or risk in {"Moderate", "High"}:
        if risk == "High":
            return "https://www.cdc.gov/hearher/index.html"
        return "https://www.cdc.gov/hearher/maternal-warning-signs/index.html"
    return "https://www.cdc.gov/pregnancy/during/index.html"


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

    def post_goal(pid, text, kind, code, cond, parent_id=None):
        status, bundle = fhir(
            "GET",
            f"/Goal?patient=Patient/{pid}&lifecycle-status=active&_count=50",
        )
        if status == 200 and isinstance(bundle, dict):
            for entry in bundle.get("entry") or []:
                resource = entry.get("resource") or {}
                if (resource.get("description") or {}).get("text") == text:
                    return resource["id"]
        goal = {
            "resourceType": "Goal",
            "lifecycleStatus": "active",
            "achievementStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/goal-achievement",
                        "code": "in-progress",
                    }
                ],
                "text": "In Progress",
            },
            "category": [
                {
                    "coding": [
                        {
                            "system": "https://langcare.example.org/fhir/CodeSystem/care-goal",
                            "code": code,
                            "display": text if kind == "major-goal" else f"{text} ({code})",
                        }
                    ],
                    "text": kind,
                }
            ],
            "description": {"text": text},
            "subject": {"reference": f"Patient/{pid}"},
            "startDate": "2026-06-15",
            "addresses": [{"reference": f"Condition/{cond}"}],
        }
        if parent_id:
            goal["note"] = [{"text": f"partOf: Goal/{parent_id}"}]
        status, body = fhir("POST", "/Goal", goal)
        if status not in (200, 201) or not isinstance(body, dict):
            raise RuntimeError(f"Goal POST {status} {body}")
        return body["id"]

    created = {}
    for row in PATIENTS:
        pid = row["pid"]
        print("==", pid)
        url = education_url(row["risk"], row["specific"])

        def qualitative_risk(display, code):
            return {
                "qualitativeRisk": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/risk-probability",
                            "code": code,
                            "display": display,
                        }
                    ],
                    "text": display,
                }
            }

        def sync_ra(row=row):
            rid = row.get("ra")
            resource = None
            if rid:
                status, resource = fhir("GET", f"/RiskAssessment/{rid}")
                if status != 200:
                    resource = None
            if resource is None:
                status, bundle = fhir(
                    "GET",
                    f"/RiskAssessment?patient=Patient/{row['pid']}&_count=20",
                )
                if status == 200 and isinstance(bundle, dict):
                    for entry in bundle.get("entry") or []:
                        found = entry.get("resource") or {}
                        codes = (found.get("code") or {}).get("coding") or []
                        if any(c.get("code") == "pregnancy-risk" for c in codes):
                            resource = found
                            rid = found.get("id")
                            break
            if resource is None:
                ra = {
                    "resourceType": "RiskAssessment",
                    "status": "final",
                    "code": {
                        "coding": [
                            {
                                "system": "https://langcare.example.org/fhir/CodeSystem/risk",
                                "code": "pregnancy-risk",
                                "display": "Pregnancy Risk Classification",
                            }
                        ],
                        "text": "Pregnancy Risk Classification",
                    },
                    "subject": {"reference": f"Patient/{row['pid']}"},
                    "occurrenceDateTime": "2026-06-15T00:00:00Z",
                    "prediction": [qualitative_risk(row["risk"], row["risk"].lower())],
                }
                status, body = fhir("POST", "/RiskAssessment", ra)
                if status not in (200, 201) or not isinstance(body, dict):
                    raise RuntimeError(f"RiskAssessment POST {status} {body}")
                return body["id"]
            version = resource["meta"]["versionId"]
            updated = strip_meta(copy.deepcopy(resource))
            preds = updated.get("prediction") or [{}]
            preds[0] = qualitative_risk(row["risk"], row["risk"].lower())
            updated["prediction"] = preds
            put_status, put_body = fhir(
                "PUT",
                f"/RiskAssessment/{rid}",
                updated,
                extra={"If-Match": f'W/"{version}"'},
            )
            if put_status not in (200, 201) or not isinstance(put_body, dict):
                raise RuntimeError(f"RiskAssessment PUT {put_status} {put_body}")
            return rid

        print("  ra", retry(sync_ra))

        cpid = row["cp"]
        if not cpid:

            def create_cp(row=row):
                cp = {
                    "resourceType": "CarePlan",
                    "status": "active",
                    "intent": "order",
                    "subject": {"reference": f"Patient/{row['pid']}"},
                    "description": WHO_DESC,
                    "instantiatesCanonical": [WHO_FULL, WHO_SHORT],
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": "http://hl7.org/fhir/us/core/CodeSystem/careplan-category",
                                    "code": "assess-plan",
                                }
                            ]
                        },
                        {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": "134435003",
                                    "display": "Routine antenatal care (regime/therapy)",
                                }
                            ],
                            "text": "Routine antenatal care (regime/therapy)",
                        },
                    ],
                    "addresses": [{"reference": f"Condition/{row['cond']}"}],
                    "activity": [],
                }
                status, body = fhir("POST", "/CarePlan", cp)
                if status not in (200, 201) or not isinstance(body, dict):
                    raise RuntimeError(f"CarePlan POST {status} {body}")
                return body["id"]

            cpid = retry(create_cp)
            row["cp"] = cpid
            print("  new careplan", cpid)

        maternal_id = retry(
            lambda row=row: post_goal(
                row["pid"], GOAL_MATERNAL, "major-goal", "maternal-mortality-reduction", row["cond"]
            )
        )
        neonatal_id = retry(
            lambda row=row: post_goal(
                row["pid"], GOAL_NEONATAL, "major-goal", "neonatal-comorbidity-reduction", row["cond"]
            )
        )
        edu_maternal = retry(
            lambda row=row, maternal_id=maternal_id: post_goal(
                row["pid"],
                "Complete assigned maternal education resource",
                "sub-goal",
                "maternal-mortality-reduction",
                row["cond"],
                maternal_id,
            )
        )
        edu_neonatal = retry(
            lambda row=row, neonatal_id=neonatal_id: post_goal(
                row["pid"],
                "Complete assigned neonatal education resource",
                "sub-goal",
                "neonatal-comorbidity-reduction",
                row["cond"],
                neonatal_id,
            )
        )
        print("  goals", maternal_id, neonatal_id, edu_maternal, edu_neonatal)

        def update_cp(
            row=row,
            cpid=cpid,
            url=url,
            maternal_id=maternal_id,
            neonatal_id=neonatal_id,
            edu_maternal=edu_maternal,
            edu_neonatal=edu_neonatal,
        ):
            status, resource = fhir("GET", f"/CarePlan/{cpid}")
            if status != 200:
                raise RuntimeError(f"CarePlan GET {status} {resource}")
            version = resource["meta"]["versionId"]
            updated = strip_meta(copy.deepcopy(resource))
            updated["status"] = "active"
            updated["intent"] = updated.get("intent") or "order"
            updated["description"] = WHO_DESC
            canons = list(updated.get("instantiatesCanonical") or [])
            if WHO_FULL not in canons:
                canons.insert(0, WHO_FULL)
            if WHO_SHORT not in canons:
                canons.append(WHO_SHORT)
            updated["instantiatesCanonical"] = canons
            updated["subject"] = {"reference": f"Patient/{row['pid']}"}
            existing_goals = [g.get("reference") for g in (updated.get("goal") or []) if g.get("reference")]
            for gid in (maternal_id, neonatal_id, edu_maternal, edu_neonatal):
                ref = f"Goal/{gid}"
                if ref not in existing_goals:
                    existing_goals.append(ref)
            updated["goal"] = [{"reference": g} for g in existing_goals]
            activities = copy.deepcopy(updated.get("activity") or [])

            def upsert_edu(desc, edu_url, code_display):
                for act in activities:
                    detail = act.get("detail") or {}
                    if detail.get("description") == desc:
                        detail["kind"] = "Task"
                        detail["status"] = "completed"
                        detail["instantiatesUri"] = [edu_url]
                        detail["performer"] = [{"reference": f"Patient/{row['pid']}"}]
                        act["detail"] = detail
                        return
                activities.append(
                    {
                        "detail": {
                            "kind": "Task",
                            "status": "completed",
                            "description": desc,
                            "instantiatesUri": [edu_url],
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://snomed.info/sct",
                                        "code": "409073007",
                                        "display": "Instruction in self-care (procedure)",
                                    }
                                ],
                                "text": code_display,
                            },
                            "performer": [{"reference": f"Patient/{row['pid']}"}],
                        }
                    }
                )

            upsert_edu(
                "Patient action: review maternal education resource",
                url,
                "Maternal education resource",
            )
            upsert_edu(
                "Patient action: review neonatal education resource",
                NEONATAL_URL,
                "Neonatal education resource",
            )
            updated["activity"] = activities
            put_status, put_body = fhir(
                "PUT",
                f"/CarePlan/{cpid}",
                updated,
                extra={"If-Match": f'W/"{version}"'},
            )
            if put_status not in (200, 201) or not isinstance(put_body, dict):
                raise RuntimeError(f"CarePlan PUT {put_status} {put_body}")
            return put_status

        print("  careplan", retry(update_cp))

        def create_doc(row=row, url=url, cpid=cpid):
            status, bundle = fhir(
                "GET",
                f"/DocumentReference?patient=Patient/{row['pid']}&_count=20",
            )
            if status == 200 and isinstance(bundle, dict):
                for entry in bundle.get("entry") or []:
                    resource = entry.get("resource") or {}
                    if (resource.get("type") or {}).get("text") == "Pregnancy education resource":
                        return resource["id"]
            doc = {
                "resourceType": "DocumentReference",
                "status": "current",
                "type": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": "61357-0",
                            "display": "Medication or education note",
                        }
                    ],
                    "text": "Pregnancy education resource",
                },
                "subject": {"reference": f"Patient/{row['pid']}"},
                "description": (
                    f"Golden education content for risk={row['risk']} "
                    f"condition={row['specific']}"
                ),
                "content": [
                    {
                        "attachment": {
                            "contentType": "text/html",
                            "title": f"{row['risk']} pregnancy education",
                            "url": url,
                        }
                    }
                ],
                "context": {
                    "related": [{"reference": f"CarePlan/{cpid}"}],
                    "event": [
                        {
                            "text": f"risk={row['risk']};condition={row['specific']}"
                        }
                    ],
                },
            }
            status, body = fhir("POST", "/DocumentReference", doc)
            if status not in (200, 201) or not isinstance(body, dict):
                raise RuntimeError(f"DocumentReference POST {status} {body}")
            return body["id"]

        def create_task(row=row, url=url, cpid=cpid):
            status, bundle = fhir(
                "GET", f"/Task?patient=Patient/{row['pid']}&_count=50"
            )
            if status == 200 and isinstance(bundle, dict):
                for entry in bundle.get("entry") or []:
                    resource = entry.get("resource") or {}
                    if (resource.get("code") or {}).get("text") == "Education resource access":
                        return resource["id"]
            task = {
                "resourceType": "Task",
                "status": "completed",
                "intent": "order",
                "code": {"text": "Education resource access"},
                "description": (
                    "Patient notified that education resources are available; "
                    "access marked complete."
                ),
                "for": {"reference": f"Patient/{row['pid']}"},
                "owner": {"reference": f"Patient/{row['pid']}"},
                "basedOn": [{"reference": f"CarePlan/{cpid}"}],
                "instantiatesUri": url,
                "output": [
                    {
                        "type": {"text": "education-url"},
                        "valueUrl": url,
                    }
                ],
                "note": [
                    {
                        "text": f"risk={row['risk']};condition={row['specific']}"
                    }
                ],
            }
            status, body = fhir("POST", "/Task", task)
            if status not in (200, 201) or not isinstance(body, dict):
                raise RuntimeError(f"Task POST {status} {body}")
            return body["id"]

        print("  doc", retry(create_doc), "task", retry(create_task))
        created[pid] = {
            "careplan": cpid,
            "maternal_goal": maternal_id,
            "neonatal_goal": neonatal_id,
            "education_url": url,
        }
        time.sleep(0.3)

    print(json.dumps(created, indent=2))
    print("waiting for stream")
    time.sleep(12)

    bq = bigquery.Client(project=PROJECT, credentials=creds)
    for table in ("CarePlan", "Goal", "RiskAssessment", "Task", "DocumentReference"):
        sql = f"""
        CREATE OR REPLACE TABLE `{PROJECT}.synth_healthcare.{table}` AS
        SELECT * FROM `{PROJECT}.synth_healthcare.{table}`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY commitTimestamp DESC) = 1
        """
        print("collapse", table)
        bq.query(sql).result()

    print(
        "pregnant without careplan",
        list(
            bq.query(
                """
        SELECT COUNT(*) AS n
        FROM `mktg-vdc-poc-r83n.synth_healthcare.Condition` c
        WHERE c.clinicalStatus.coding[SAFE_OFFSET(0)].code = 'active'
          AND c.code.coding[SAFE_OFFSET(0)].code = '72892002'
          AND NOT EXISTS (
            SELECT 1 FROM `mktg-vdc-poc-r83n.synth_healthcare.CarePlan` cp
            WHERE cp.subject.patientId = c.subject.patientId AND cp.status = 'active'
          )
        """
            )
        )[0].n,
    )


if __name__ == "__main__":
    main()
