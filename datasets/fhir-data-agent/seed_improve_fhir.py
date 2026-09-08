"""Fill missing WHO ANC8 CareTeam, pathway Goal, and patient-action activities."""

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
WHO_GOAL = "Complete the WHO 8-contact antenatal care pathway"
WHO_ACTION = (
    "Patient action: complete antenatal education for the WHO 8-contact pathway."
)
PRACTITIONER = "a137d589-bcc5-4e4e-a4e4-40a27a0d97b0"
ORGANIZATION = "4792af84-2da5-4eaf-b97b-b565614b5475"
DUP_GA = "bae0fa2a-e060-42b1-87c8-2bc067b8ad58"

PATIENTS = [
    {
        "pid": "2bae212d-9da5-4b31-957f-86f058f84503",
        "cp": "4612770b-5197-4578-a07a-9f2674cc66e3",
        "cond": "9dacfb25-78f1-4ffc-a084-ce02d2092b24",
        "need_team": True,
        "need_who_goal": True,
        "need_who_action": True,
    },
    {
        "pid": "7a1c7fda-6b1a-44ff-b694-08ac926564c1",
        "cp": "35dec952-71ca-48f4-87a3-a895221a28ef",
        "cond": "4db28a4e-81e1-4588-a4e8-79195b11c4e5",
        "need_team": True,
        "need_who_goal": True,
        "need_who_action": True,
    },
    {
        "pid": "e81035c5-f3fa-42ad-88a0-b58a1ea6c994",
        "cp": "c60df24d-6422-46b9-bad5-7f6fac9cc00b",
        "cond": "67a33a30-7e95-46de-997b-08334edb66dc",
        "need_team": False,
        "need_who_goal": True,
        "need_who_action": True,
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

    def patient_display(pid):
        status, resource = fhir("GET", f"/Patient/{pid}")
        if status != 200 or not isinstance(resource, dict):
            return f"Patient/{pid}"
        name = (resource.get("name") or [{}])[0]
        given = " ".join(name.get("given") or [])
        family = name.get("family") or ""
        prefix = " ".join(name.get("prefix") or [])
        return " ".join(part for part in (prefix, given, family) if part).strip()

    def ensure_who_goal(pid, cond):
        status, bundle = fhir(
            "GET", f"/Goal?patient=Patient/{pid}&lifecycle-status=active&_count=50"
        )
        if status == 200 and isinstance(bundle, dict):
            for entry in bundle.get("entry") or []:
                resource = entry.get("resource") or {}
                if (resource.get("description") or {}).get("text") == WHO_GOAL:
                    return resource["id"]
        body = {
            "resourceType": "Goal",
            "lifecycleStatus": "active",
            "category": [
                {
                    "coding": [
                        {
                            "system": "https://langcare.example.org/fhir/CodeSystem/care-goal",
                            "code": "who-anc8",
                            "display": WHO_GOAL,
                        }
                    ],
                    "text": "who-anc8",
                }
            ],
            "description": {"text": WHO_GOAL},
            "subject": {"reference": f"Patient/{pid}"},
            "startDate": "2026-06-15",
            "addresses": [{"reference": f"Condition/{cond}"}],
        }
        status, resp = fhir("POST", "/Goal", body)
        if status not in (200, 201) or not isinstance(resp, dict):
            raise RuntimeError(f"Goal POST {status} {resp}")
        return resp["id"]

    def ensure_team(pid, display):
        status, bundle = fhir("GET", f"/CareTeam?patient=Patient/{pid}&status=active&_count=20")
        if status == 200 and isinstance(bundle, dict):
            for entry in bundle.get("entry") or []:
                resource = entry.get("resource") or {}
                if len(resource.get("participant") or []) >= 3:
                    return resource["id"]
        body = {
            "resourceType": "CareTeam",
            "status": "active",
            "name": "WHO ANC8 antenatal care team",
            "subject": {"reference": f"Patient/{pid}", "display": display},
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": "134435003",
                            "display": "Routine antenatal care (regime/therapy)",
                        }
                    ],
                    "text": "Routine antenatal care",
                }
            ],
            "participant": [
                {
                    "role": [
                        {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": "116154003",
                                    "display": "Patient",
                                }
                            ],
                            "text": "Patient",
                        }
                    ],
                    "member": {
                        "reference": f"Patient/{pid}",
                        "display": display,
                    },
                },
                {
                    "role": [
                        {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": "223366009",
                                    "display": "Healthcare professional (occupation)",
                                }
                            ],
                            "text": "Healthcare professional (occupation)",
                        }
                    ],
                    "member": {
                        "reference": f"Practitioner/{PRACTITIONER}",
                        "display": "Dr. Alleen813 Anderson154",
                    },
                },
                {
                    "role": [
                        {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": "224891009",
                                    "display": "Healthcare services (qualifier value)",
                                }
                            ],
                            "text": "Healthcare services (qualifier value)",
                        }
                    ],
                    "member": {
                        "reference": f"Organization/{ORGANIZATION}",
                        "display": "VANDERBILT STALLWORTH REHABILITATION HOSPITAL LP",
                    },
                },
            ],
        }
        status, resp = fhir("POST", "/CareTeam", body)
        if status not in (200, 201) or not isinstance(resp, dict):
            raise RuntimeError(f"CareTeam POST {status} {resp}")
        return resp["id"]

    def update_careplan(row, goal_id, team_id):
        status, resource = fhir("GET", f"/CarePlan/{row['cp']}")
        if status != 200 or not isinstance(resource, dict):
            raise RuntimeError(f"CarePlan GET {status} {resource}")
        version = resource["meta"]["versionId"]
        updated = strip_meta(copy.deepcopy(resource))
        updated["status"] = "active"
        updated["subject"] = {"reference": f"Patient/{row['pid']}"}
        goals = [g.get("reference") for g in (updated.get("goal") or []) if g.get("reference")]
        if goal_id:
            ref = f"Goal/{goal_id}"
            if ref not in goals:
                goals.append(ref)
        updated["goal"] = [{"reference": g} for g in goals]
        if team_id:
            teams = [
                t.get("reference")
                for t in (updated.get("careTeam") or [])
                if t.get("reference")
            ]
            ref = f"CareTeam/{team_id}"
            if ref not in teams:
                teams.append(ref)
            updated["careTeam"] = [{"reference": t} for t in teams]
        if row["need_who_action"]:
            activities = copy.deepcopy(updated.get("activity") or [])
            if not any(
                (a.get("detail") or {}).get("description") == WHO_ACTION for a in activities
            ):
                activities.append(
                    {
                        "detail": {
                            "kind": "Task",
                            "status": "in-progress",
                            "description": WHO_ACTION,
                            "performer": [{"reference": f"Patient/{row['pid']}"}],
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

    created = {}
    for row in PATIENTS:
        pid = row["pid"]
        display = patient_display(pid)
        print("==", pid, display)
        goal_id = None
        if row["need_who_goal"]:
            goal_id = retry(lambda row=row: ensure_who_goal(row["pid"], row["cond"]))
            print("  who goal", goal_id)
        team_id = None
        if row["need_team"]:
            team_id = retry(lambda pid=pid, display=display: ensure_team(pid, display))
            print("  team", team_id)
        print("  careplan", retry(lambda row=row, goal_id=goal_id, team_id=team_id: update_careplan(row, goal_id, team_id)))
        created[pid] = {"goal": goal_id, "team": team_id}

    status, _ = fhir("GET", f"/Observation/{DUP_GA}")
    if status == 200:
        del_status, del_body = fhir("DELETE", f"/Observation/{DUP_GA}")
        print("delete dup GA", DUP_GA, del_status)

    print(json.dumps(created, indent=2))
    print("waiting for stream")
    time.sleep(16)
    bq = bigquery.Client(project=PROJECT, credentials=creds)
    for table in ("CarePlan", "Goal", "CareTeam", "Observation"):
        print("collapse", table)
        bq.query(
            f"""
        CREATE OR REPLACE TABLE `{PROJECT}.synth_healthcare.{table}` AS
        SELECT * FROM `{PROJECT}.synth_healthcare.{table}`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY commitTimestamp DESC) = 1
        """
        ).result()
    # Drop the deleted duplicate from the current-state snapshot if DELETE streamed.
    bq.query(
        f"""
        CREATE OR REPLACE TABLE `{PROJECT}.synth_healthcare.Observation` AS
        SELECT * FROM `{PROJECT}.synth_healthcare.Observation`
        WHERE id != '{DUP_GA}'
        """
    ).result()


if __name__ == "__main__":
    main()
