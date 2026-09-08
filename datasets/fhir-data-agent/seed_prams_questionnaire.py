"""Complete the CDC PRAMS Phase 9.2 Questionnaire for every pregnant patient."""

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
QUESTIONNAIRE_ID = "1eb98103-88ef-411c-8d5b-1dce22f6dbd5"
QUESTIONNAIRE_URL = "https://example.org/fhir/Questionnaire/cdc-prams-phase9-2-core"
QUESTIONNAIRE_REF = f"Questionnaire/{QUESTIONNAIRE_ID}"
AUTHORED = "2026-09-07T12:00:00+00:00"
COMPLETION_DATE = "2026-09-07"
ACTION_DESC = "Patient action: complete the CDC PRAMS Phase 9.2 Core Questionnaire"
TASK_CODE = "PRAMS questionnaire completion"

PATIENTS = [
    {
        "pid": "74ee3ce8-e896-433b-bb89-43c8ad5b333a",
        "cp": "e7b5bdec-76e5-4d97-9725-a43c29978af1",
        "risk": "Moderate",
        "specific": "59621000",
        "birthDate": "1996-02-26",
        "qr": None,
    },
    {
        "pid": "9b553331-8f4a-43c1-b83f-55c6aa859de4",
        "cp": "386a9ae4-700d-4bbb-92d2-608e3e3e70ae",
        "risk": "Low",
        "specific": "72892002",
        "birthDate": "1995-07-17",
        "qr": None,
    },
    {
        "pid": "ac2deca4-3467-4fa2-bf84-ae74289ef331",
        "cp": "d81645b6-8354-4cd5-9e4b-2fa552d910f7",
        "risk": "High",
        "specific": "72892002",
        "birthDate": "1993-03-22",
        "qr": None,
    },
    {
        "pid": "d4a31e4f-2c79-4a7f-845b-519ef3c1f511",
        "cp": "aaa5d20e-41f7-498f-a509-f264d0878b2e",
        "risk": "Moderate",
        "specific": "72892002",
        "birthDate": "2007-06-16",
        "qr": "608e2aae-e8ea-41be-bf6a-fc486d8134b5",
    },
    {
        "pid": "2bae212d-9da5-4b31-957f-86f058f84503",
        "cp": "4612770b-5197-4578-a07a-9f2674cc66e3",
        "risk": "Low",
        "specific": "72892002",
        "birthDate": "1983-11-04",
        "qr": None,
    },
    {
        "pid": "e81035c5-f3fa-42ad-88a0-b58a1ea6c994",
        "cp": "c60df24d-6422-46b9-bad5-7f6fac9cc00b",
        "risk": "Low",
        "specific": "72892002",
        "birthDate": "2006-12-23",
        "qr": None,
    },
    {
        "pid": "7a1c7fda-6b1a-44ff-b694-08ac926564c1",
        "cp": "35dec952-71ca-48f4-87a3-a895221a28ef",
        "risk": "Low",
        "specific": "72892002",
        "birthDate": "2004-04-28",
        "qr": None,
    },
]

CHOICE_DEFAULTS = {
    "core-6": "private",
    "core-7": "private",
    "core-8": "private",
    "core-9": "then",
    "core-13-a": "during",
    "core-13-b": "during",
    "core-13-c": "not-received",
    "core-20": "none",
    "core-21": "none",
    "core-22": "none",
    "core-24": "none",
    "core-25": "none",
    "core-32": "not-hospital",
    "core-35": "none",
    "core-37": "never",
    "core-41": "pregnant",
    "core-42": "wants-pregnancy",
    "core-43": "condom",
    "core-46": "never",
    "core-47": "never",
    "core-48": "never",
    "core-49": "never",
    "core-51-a": "never",
    "core-51-b": "never",
    "core-54": "never",
    "core-56": "32001-37000",
}

TRUE_PREFIXES = (
    "core-4-a",
    "core-4-b",
    "core-5-",
    "core-10",
    "core-11-",
    "core-12-",
    "core-18-a",
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


def walk_items(items, section=None):
    for item in items or []:
        item_type = item.get("type")
        current_section = section
        if item_type == "group" and (item.get("linkId") or "").startswith("section-"):
            current_section = item
            yield current_section, None
        elif item_type and item_type != "group":
            yield current_section, item
        yield from walk_items(item.get("item"), current_section)


def coding_answer(code, options):
    for option in options or []:
        coding = option.get("valueCoding") or {}
        if coding.get("code") == code:
            return {"valueCoding": coding}
    if options:
        return {"valueCoding": (options[0].get("valueCoding") or {})}
    return {"valueString": code}


def answer_for(item, patient):
    link_id = item.get("linkId")
    item_type = item.get("type")
    options = item.get("answerOption") or []
    has_htn = patient["specific"] == "59621000"
    high = patient["risk"] == "High"
    moderate_or_high = patient["risk"] in {"Moderate", "High"}

    if link_id == "core-1":
        return {"valueDate": patient["birthDate"]}
    if link_id == "core-3-b":
        return {"valueBoolean": has_htn}
    if link_id == "core-15-b":
        return {"valueBoolean": high}
    if link_id == "core-17":
        return {"valueBoolean": moderate_or_high}
    if link_id == "core-18-c":
        return {"valueBoolean": moderate_or_high}
    if link_id == "core-41":
        return coding_answer("pregnant", options)
    if link_id == "core-58":
        return {"valueDate": COMPLETION_DATE}
    if link_id == "core-57":
        return {"valueInteger": 2}
    if item_type == "boolean":
        if link_id == "core-10" or any(
            link_id == prefix or link_id.startswith(prefix)
            for prefix in TRUE_PREFIXES
        ):
            return {"valueBoolean": True}
        return {"valueBoolean": False}
    if item_type == "choice":
        return coding_answer(CHOICE_DEFAULTS.get(link_id, "none"), options)
    if item_type == "integer":
        return {"valueInteger": 0}
    if item_type == "date":
        return {"valueDate": COMPLETION_DATE}
    if item_type == "string":
        return None
    return None


def build_response_items(questionnaire, patient):
    sections = {}
    order = []
    for section, leaf in walk_items(questionnaire.get("item") or []):
        if section is None:
            continue
        sid = section["linkId"]
        if sid not in sections:
            sections[sid] = {
                "linkId": sid,
                "text": section.get("text"),
                "item": [],
            }
            order.append(sid)
        if leaf is None:
            continue
        value = answer_for(leaf, patient)
        if value is None:
            continue
        sections[sid]["item"].append(
            {
                "linkId": leaf["linkId"],
                "text": leaf.get("text"),
                "answer": [value],
            }
        )
    return [sections[sid] for sid in order]


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

    def patient_display(pid):
        status, resource = fhir("GET", f"/Patient/{pid}")
        if status != 200 or not isinstance(resource, dict):
            return f"Patient/{pid}"
        name = (resource.get("name") or [{}])[0]
        given = " ".join(name.get("given") or [])
        family = name.get("family") or ""
        prefix = " ".join(name.get("prefix") or [])
        return " ".join(part for part in (prefix, given, family) if part).strip()

    status, questionnaire = fhir("GET", f"/Questionnaire/{QUESTIONNAIRE_ID}")
    if status != 200 or not isinstance(questionnaire, dict):
        raise RuntimeError(f"Questionnaire GET {status} {questionnaire}")

    created = {}
    for row in PATIENTS:
        pid = row["pid"]
        display = patient_display(pid)
        items = build_response_items(questionnaire, row)

        def find_existing(row=row, pid=pid):
            if row.get("qr"):
                status, resource = fhir("GET", f"/QuestionnaireResponse/{row['qr']}")
                if status == 200 and isinstance(resource, dict):
                    return resource
            status, bundle = fhir(
                "GET",
                f"/QuestionnaireResponse?patient=Patient/{pid}&questionnaire={QUESTIONNAIRE_REF}&_count=20",
            )
            if status == 200 and isinstance(bundle, dict):
                for entry in bundle.get("entry") or []:
                    resource = entry.get("resource") or {}
                    if resource.get("resourceType") == "QuestionnaireResponse":
                        return resource
            return None

        existing = retry(find_existing)

        def write_qr(existing=existing, display=display, items=items, row=row, pid=pid):
            payload = {
                "resourceType": "QuestionnaireResponse",
                "questionnaire": QUESTIONNAIRE_REF,
                "status": "completed",
                "authored": AUTHORED,
                "subject": {
                    "reference": f"Patient/{pid}",
                    "display": display,
                },
                "source": {"reference": f"Patient/{pid}"},
                "basedOn": [{"reference": f"CarePlan/{row['cp']}"}],
                "item": items,
            }
            if existing:
                version = (existing.get("meta") or {}).get("versionId")
                payload["id"] = existing["id"]
                extra = {"If-Match": f'W/"{version}"'} if version else None
                status, body = fhir(
                    "PUT",
                    f"/QuestionnaireResponse/{existing['id']}",
                    payload,
                    extra=extra,
                )
            else:
                status, body = fhir("POST", "/QuestionnaireResponse", payload)
            if status not in (200, 201) or not isinstance(body, dict):
                raise RuntimeError(f"QuestionnaireResponse write {status} {body}")
            return body["id"]

        qr_id = retry(write_qr)
        print("  qr", pid, qr_id)

        def update_cp(row=row, pid=pid):
            status, resource = fhir("GET", f"/CarePlan/{row['cp']}")
            if status != 200:
                raise RuntimeError(f"CarePlan GET {status} {resource}")
            version = resource["meta"]["versionId"]
            updated = strip_meta(copy.deepcopy(resource))
            activities = copy.deepcopy(updated.get("activity") or [])
            found = False
            for act in activities:
                detail = act.get("detail") or {}
                if detail.get("description") == ACTION_DESC:
                    detail["kind"] = "Task"
                    detail["status"] = "completed"
                    detail["instantiatesUri"] = [QUESTIONNAIRE_URL]
                    detail["performer"] = [{"reference": f"Patient/{pid}"}]
                    act["detail"] = detail
                    found = True
                    break
            if not found:
                activities.append(
                    {
                        "detail": {
                            "kind": "Task",
                            "status": "completed",
                            "description": ACTION_DESC,
                            "instantiatesUri": [QUESTIONNAIRE_URL],
                            "code": {"text": TASK_CODE},
                            "performer": [{"reference": f"Patient/{pid}"}],
                        }
                    }
                )
            updated["activity"] = activities
            put_status, put_body = fhir(
                "PUT",
                f"/CarePlan/{row['cp']}",
                updated,
                extra={"If-Match": f'W/"{version}"'},
            )
            if put_status not in (200, 201) or not isinstance(put_body, dict):
                raise RuntimeError(f"CarePlan PUT {put_status} {put_body}")
            return put_status

        def create_task(row=row, pid=pid, qr_id=qr_id):
            status, bundle = fhir("GET", f"/Task?patient=Patient/{pid}&_count=50")
            if status == 200 and isinstance(bundle, dict):
                for entry in bundle.get("entry") or []:
                    resource = entry.get("resource") or {}
                    if (resource.get("code") or {}).get("text") == TASK_CODE:
                        return resource["id"]
            task = {
                "resourceType": "Task",
                "status": "completed",
                "intent": "order",
                "code": {"text": TASK_CODE},
                "description": (
                    "Patient completed the CDC PRAMS Phase 9.2 Core Questionnaire."
                ),
                "for": {"reference": f"Patient/{pid}"},
                "owner": {"reference": f"Patient/{pid}"},
                "focus": {"reference": f"QuestionnaireResponse/{qr_id}"},
                "basedOn": [{"reference": f"CarePlan/{row['cp']}"}],
                "instantiatesUri": QUESTIONNAIRE_URL,
            }
            status, body = fhir("POST", "/Task", task)
            if status not in (200, 201) or not isinstance(body, dict):
                raise RuntimeError(f"Task POST {status} {body}")
            return body["id"]

        print("  careplan", retry(update_cp), "task", retry(create_task))
        created[pid] = {"questionnaire_response": qr_id, "careplan": row["cp"]}
        time.sleep(0.3)

    print(json.dumps(created, indent=2))
    print("waiting for stream")
    time.sleep(16)

    bq = bigquery.Client(project=PROJECT, credentials=creds)
    job_config = bigquery.QueryJobConfig(labels={"datacloud": "cursor"})
    for table in ("QuestionnaireResponse", "CarePlan", "Task"):
        print("collapse", table)
        bq.query(
            f"""
        CREATE OR REPLACE TABLE `{PROJECT}.synth_healthcare.{table}` AS
        SELECT * FROM `{PROJECT}.synth_healthcare.{table}`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY commitTimestamp DESC) = 1
        """,
            job_config=job_config,
        ).result()

    check = list(
        bq.query(
            f"""
        SELECT COUNT(*) AS n
        FROM `{PROJECT}.synth_healthcare.Condition` c
        WHERE c.clinicalStatus.coding[SAFE_OFFSET(0)].code = 'active'
          AND c.code.coding[SAFE_OFFSET(0)].code = '72892002'
          AND NOT EXISTS (
            SELECT 1
            FROM `{PROJECT}.synth_healthcare.QuestionnaireResponse` qr
            WHERE qr.subject.patientId = c.subject.patientId
              AND qr.status = 'completed'
              AND qr.questionnaire = '{QUESTIONNAIRE_REF}'
          )
        """,
            job_config=job_config,
        ).result()
    )
    print("pregnant without completed PRAMS", [dict(r) for r in check])


if __name__ == "__main__":
    main()
