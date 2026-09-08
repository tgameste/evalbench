"""Seed WHO ANC8 ActivityDefinitions with R4 who/what/when/where/why bindings."""

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
PLAN_ID = "9dbd5bef-7198-41f9-a575-9e1beff90df9"
WHO_GUIDELINE = "https://www.who.int/publications/i/item/9789241549912"
SNOMED = "http://snomed.info/sct"
TOPIC = "http://terminology.hl7.org/CodeSystem/definition-topic"
RESOURCE_TYPES = "http://hl7.org/fhir/resource-types"

# R4-valid bindings only. demo-r4 rejects R5 versionAlgorithm, asNeeded,
# participant.function, and ActionParticipantType values added in R5
# (organization, careteam, health-care-worker). R4 allows only patient,
# practitioner, related-person, and device.
R4_PARTICIPANT_TYPES = frozenset(
    {"patient", "practitioner", "related-person", "device"}
)
CATALOG = {
    "practice-blood-pressure": {
        "kind": "ServiceRequest",
        "code": ("75367002", "Blood pressure taking (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
        "body_site": ("368209003", "Right upper arm structure"),
    },
    "practice-proteinuria": {
        "kind": "ServiceRequest",
        "code": ("167330003", "Urine protein test (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "practice-weight": {
        "kind": "ServiceRequest",
        "code": ("363808001", "Measurement of body weight (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
        "body_site": ("38266002", "Entire body as a whole"),
    },
    "practice-warning-signs": {
        "kind": "CommunicationRequest",
        "code": ("311401005", "Patient education (procedure)"),
        "topic": "education",
        "participant_type": "practitioner",
        "role": ("309343006", "Physician"),
    },
    "practice-fetal-heart": {
        "kind": "ServiceRequest",
        "code": ("268480007", "Fetal heart monitoring (regime/therapy)"),
        "topic": "assessment",
        "role": ("224535009", "Midwife"),
        "body_site": ("83418008", "Entire fetus"),
    },
    "practice-birth-preparedness": {
        "kind": "CommunicationRequest",
        "code": ("409073007", "Instruction in self-care (procedure)"),
        "topic": "education",
        "role": ("224535009", "Midwife"),
    },
    "nutrition-healthy-diet-activity": {
        "kind": "CommunicationRequest",
        "code": ("11816003", "Diet education (procedure)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
    },
    "nutrition-energy-protein-education": {
        "kind": "CommunicationRequest",
        "code": ("11816003", "Diet education (procedure)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
    },
    "iron-folic-acid-daily": {
        "kind": "MedicationRequest",
        "code": ("281789004", "Iron supplement therapy (procedure)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("387390002", "Iron + folic acid"),
    },
    "iron-folic-acid-intermittent": {
        "kind": "MedicationRequest",
        "code": ("281789004", "Iron supplement therapy (procedure)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("387390002", "Iron + folic acid"),
    },
    "balanced-energy-protein-supplement": {
        "kind": "MedicationRequest",
        "code": ("182922004", "Dietary regime (regime/therapy)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("226365001", "Food supplement"),
    },
    "calcium-supplement": {
        "kind": "MedicationRequest",
        "code": ("281790008", "Calcium supplement therapy (procedure)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("387307005", "Calcium"),
    },
    "vitamin-a-supplement": {
        "kind": "MedicationRequest",
        "code": ("281791007", "Vitamin supplement therapy (procedure)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("259333003", "Vitamin A"),
    },
    "reduce-caffeine": {
        "kind": "CommunicationRequest",
        "code": ("11816003", "Diet education (procedure)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
    },
    "anaemia-assessment": {
        "kind": "ServiceRequest",
        "code": ("269828009", "Hemoglobin measurement (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "asb-screening": {
        "kind": "ServiceRequest",
        "code": ("252385000", "Urine culture (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "asb-antibiotic-treatment": {
        "kind": "MedicationRequest",
        "code": ("281789009", "Antimicrobial therapy (procedure)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("373270004", "Antibacterial"),
    },
    "ipv-clinical-enquiry": {
        "kind": "ServiceRequest",
        "code": ("225337009", "Domestic abuse screening (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "hyperglycaemia-classification": {
        "kind": "ServiceRequest",
        "code": ("113076002", "Glucose measurement (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "tobacco-screening": {
        "kind": "ServiceRequest",
        "code": ("171209009", "Tobacco use screening (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "substance-use-screening": {
        "kind": "ServiceRequest",
        "code": ("171207006", "Alcohol consumption screening (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "hiv-syphilis-testing": {
        "kind": "ServiceRequest",
        "code": ("171121004", "HIV screening (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "tb-screening": {
        "kind": "ServiceRequest",
        "code": ("171126009", "Tuberculosis screening (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
    },
    "early-ultrasound": {
        "kind": "ServiceRequest",
        "code": ("268445003", "Ultrasound scan for fetal growth (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
        "body_site": ("181469002", "Entire uterus"),
    },
    "fetal-growth-assessment": {
        "kind": "ServiceRequest",
        "code": ("169228004", "Antenatal ultrasound scan (procedure)"),
        "topic": "assessment",
        "role": ("309343006", "Physician"),
        "body_site": ("83418008", "Entire fetus"),
    },
    "tetanus-vaccination": {
        "kind": "ImmunizationRecommendation",
        "code": ("333598008", "Tetanus vaccine (product)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("333598008", "Tetanus vaccine"),
    },
    "hiv-prep": {
        "kind": "MedicationRequest",
        "code": ("713577000", "Pre-exposure prophylaxis against HIV (procedure)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("713577000", "HIV pre-exposure prophylaxis"),
    },
    "malaria-iptp": {
        "kind": "MedicationRequest",
        "code": ("186788009", "Malaria prophylaxis (procedure)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("387406002", "Sulfadoxine + pyrimethamine"),
    },
    "anthelminthic-prevention": {
        "kind": "MedicationRequest",
        "code": ("281792000", "Anthelmintic therapy (procedure)"),
        "topic": "treatment",
        "role": ("309343006", "Physician"),
        "product": ("387326001", "Anthelmintic"),
    },
    "nausea-vomiting-relief": {
        "kind": "CommunicationRequest",
        "code": ("386373004", "Nutrition management (regime/therapy)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
    },
    "heartburn-relief": {
        "kind": "CommunicationRequest",
        "code": ("386373004", "Nutrition management (regime/therapy)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
    },
    "leg-cramp-relief": {
        "kind": "CommunicationRequest",
        "code": ("386373004", "Nutrition management (regime/therapy)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
        "body_site": ("182281004", "Entire lower limb"),
    },
    "back-pelvic-pain": {
        "kind": "CommunicationRequest",
        "code": ("229064005", "Physiotherapy education (procedure)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
        "body_site": ("12921003", "Pelvic structure"),
    },
    "constipation-relief": {
        "kind": "CommunicationRequest",
        "code": ("386373004", "Nutrition management (regime/therapy)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
    },
    "varicose-oedema-relief": {
        "kind": "CommunicationRequest",
        "code": ("229064005", "Physiotherapy education (procedure)"),
        "topic": "education",
        "role": ("309343006", "Physician"),
        "body_site": ("182281004", "Entire lower limb"),
    },
    "woman-held-case-notes": {
        "kind": "Task",
        "code": ("371525003", "Clinical documentation (procedure)"),
        "topic": "education",
        "participant_type": "patient",
        "role": ("116154003", "Patient"),
    },
    "midwife-continuity": {
        "kind": "ServiceRequest",
        "code": ("424525001", "Antenatal care (regime/therapy)"),
        "topic": "treatment",
        "role": ("224535009", "Midwife"),
    },
    "community-pla": {
        "kind": "Task",
        "code": ("410606002", "Social service procedure (procedure)"),
        "topic": "education",
        "participant_type": "practitioner",
        "role": ("303119007", "Community health services"),
    },
    "community-home-visits": {
        "kind": "ServiceRequest",
        "code": ("439708006", "Home visit (procedure)"),
        "topic": "assessment",
        "role": ("224535009", "Midwife"),
    },
    "task-shift-health-promotion": {
        "kind": "Task",
        "code": ("311401005", "Patient education (procedure)"),
        "topic": "education",
        "participant_type": "practitioner",
        "role": ("303119007", "Community health services"),
    },
    "task-shift-supplements-iptp": {
        "kind": "Task",
        "code": ("385763008", "Health promotion (procedure)"),
        "topic": "treatment",
        "participant_type": "practitioner",
        "role": ("303119007", "Community health services"),
    },
    "rural-workforce-support": {
        "kind": "Task",
        "code": ("385763008", "Health promotion (procedure)"),
        "topic": "treatment",
        "participant_type": "practitioner",
        "role": ("303119007", "Community health services"),
    },
    "eight-contact-schedule": {
        "kind": "Appointment",
        "code": ("424525001", "Antenatal care (regime/therapy)"),
        "topic": "assessment",
        "role": ("224535009", "Midwife"),
    },
}


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


def camel(slug: str) -> str:
    return "".join(part.title() for part in slug.replace("-", "_").split("_"))


def collect_plan_activities(plan: dict) -> dict[str, dict]:
    found: dict[str, dict] = {}

    def walk(actions, week=None):
        for action in actions or []:
            current_week = week
            for ext in action.get("extension") or []:
                if str(ext.get("url") or "").endswith("target-gestational-week"):
                    current_week = ext.get("valueInteger")
            canonical = action.get("definitionCanonical") or ""
            if canonical:
                url = canonical.split("|", 1)[0]
                version = canonical.split("|", 1)[1] if "|" in canonical else "1.0.0"
                rec_type = rec_id = None
                for ext in action.get("extension") or []:
                    ext_url = str(ext.get("url") or "")
                    if ext_url.endswith("who-anc-recommendation-type"):
                        rec_type = ext.get("valueCode")
                    if ext_url.endswith("who-anc-recommendation-id"):
                        rec_id = ext.get("valueString")
                row = found.setdefault(
                    url,
                    {
                        "url": url,
                        "version": version,
                        "slug": url.rsplit("/", 1)[-1],
                        "title": action.get("title"),
                        "description": action.get("description"),
                        "rec_types": set(),
                        "rec_ids": set(),
                        "weeks": set(),
                    },
                )
                if rec_type:
                    row["rec_types"].add(rec_type)
                if rec_id:
                    row["rec_ids"].add(rec_id)
                if current_week is not None:
                    row["weeks"].add(current_week)
                if action.get("description") and not row["description"]:
                    row["description"] = action.get("description")
            walk(action.get("action") or [], current_week)

    walk(plan.get("action") or [])
    return found


def coding(system: str, code: str, display: str | None = None) -> dict:
    value = {"system": system, "code": code}
    if display:
        value["display"] = display
    return value


def build_activity(meta: dict) -> dict:
    slug = meta["slug"]
    spec = CATALOG.get(slug) or {}
    kind = spec.get("kind") or "ServiceRequest"
    code = spec.get("code") or ("424525001", "Antenatal care (regime/therapy)")
    topic = spec.get("topic") or "assessment"
    participant_type = spec.get("participant_type") or "practitioner"
    if participant_type not in R4_PARTICIPANT_TYPES:
        participant_type = "practitioner"
    role = spec.get("role") or ("309343006", "Physician")
    weeks = sorted(meta["weeks"])
    rec_types = sorted(meta["rec_types"])
    rec_ids = sorted(meta["rec_ids"])
    why = meta.get("description") or (
        f"WHO ANC8 definitional template for {meta['title']}."
    )
    when = (
        f"Apply at WHO ANC contacts covering gestational weeks {', '.join(map(str, weeks))}."
        if weeks
        else "Apply when the enclosing PlanDefinition action is selected."
    )
    resource = {
        "resourceType": "ActivityDefinition",
        "url": meta["url"],
        "identifier": [
            {
                "use": "official",
                "system": "https://langcare.example.org/fhir/ActivityDefinition",
                "value": slug,
            }
        ],
        "version": meta["version"],
        "name": camel(slug),
        "title": meta["title"],
        "status": "active",
        "experimental": False,
        "date": "2026-08-31T00:00:00Z",
        "publisher": "LangCare implementation of WHO guidance",
        "description": why,
        "purpose": (
            "Reusable patient-independent template for a WHO ANC8 activity. "
            "Universal who/what/when/where/why live here; PlanDefinition/who-anc8 "
            "adds contact-specific grouping. This definition does not itself authorize an order."
        ),
        "usage": (
            f"{when} Recommendation type={','.join(rec_types) or 'unspecified'}; "
            f"WHO id={','.join(rec_ids) or 'n/a'}."
        ),
        "jurisdiction": [
            {"coding": [coding("urn:iso:std:iso:3166", "US")]}
        ],
        "topic": [
            {
                "coding": [coding(TOPIC, topic, topic.title())],
                "text": f"WHO ANC8 {topic}",
            }
        ],
        "author": [{"name": "LangCare implementation of WHO guidance"}],
        "relatedArtifact": [
            {
                "type": "documentation",
                "display": "WHO 2016 ANC guideline",
                "url": WHO_GUIDELINE,
            }
        ],
        "kind": kind,
        "intent": "proposal",
        "priority": "routine" if "essential-practice" not in rec_types else "urgent",
        "code": {
            "coding": [coding(SNOMED, code[0], code[1])],
            "text": code[1],
        },
        "subjectCodeableConcept": {
            "coding": [coding(RESOURCE_TYPES, "Patient", "Patient")]
        },
        "timingTiming": {
            "code": {"text": when},
            "extension": [
                {
                    "url": "http://hl7.org/fhir/StructureDefinition/cqf-expression",
                    "valueExpression": {
                        "language": "text/cql",
                        "expression": "Now()",
                    },
                }
            ],
        },
        "participant": [
            {
                "type": participant_type,
                "role": {
                    "coding": [coding(SNOMED, role[0], role[1])],
                    "text": role[1],
                },
            }
        ],
        "useContext": [
            {
                "code": {
                    "system": "http://terminology.hl7.org/CodeSystem/usage-context-type",
                    "code": "focus",
                },
                "valueCodeableConcept": {
                    "coding": [coding(SNOMED, "77386006", "Pregnancy (finding)")],
                    "text": "Pregnancy",
                },
            },
            {
                "code": {
                    "system": "http://terminology.hl7.org/CodeSystem/usage-context-type",
                    "code": "user",
                },
                "valueCodeableConcept": {
                    "coding": [coding(SNOMED, role[0], role[1])],
                    "text": role[1],
                },
            },
            {
                "code": {
                    "system": "http://terminology.hl7.org/CodeSystem/usage-context-type",
                    "code": "venue",
                },
                "valueCodeableConcept": {
                    "coding": [coding(SNOMED, "440655000", "Outpatient environment")],
                    "text": "Outpatient environment",
                },
            },
        ],
    }
    if spec.get("product"):
        product_code, product_display = spec["product"]
        resource["productCodeableConcept"] = {
            "coding": [coding(SNOMED, product_code, product_display)],
            "text": product_display,
        }
    if spec.get("body_site"):
        site_code, site_display = spec["body_site"]
        resource["bodySite"] = [
            {
                "coding": [coding(SNOMED, site_code, site_display)],
                "text": site_display,
            }
        ]
    return resource


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

    status, plan = fhir("GET", f"/PlanDefinition/{PLAN_ID}")
    if status != 200 or not isinstance(plan, dict):
        raise RuntimeError(f"PlanDefinition GET {status} {plan}")

    activities = collect_plan_activities(plan)
    print("unique ActivityDefinition canonicals", len(activities))

    created = {}
    for url, meta in sorted(activities.items()):
        payload = build_activity(meta)

        def upsert(url=url, payload=payload, meta=meta):
            status, bundle = fhir(
                "GET", f"/ActivityDefinition?url={url}&_count=5"
            )
            existing = None
            if status == 200 and isinstance(bundle, dict):
                for entry in bundle.get("entry") or []:
                    resource = entry.get("resource") or {}
                    if resource.get("url") == url:
                        existing = resource
                        break
            if existing:
                version = (existing.get("meta") or {}).get("versionId")
                payload["id"] = existing["id"]
                extra = {"If-Match": f'W/"{version}"'} if version else None
                put_status, body = fhir(
                    "PUT",
                    f"/ActivityDefinition/{existing['id']}",
                    payload,
                    extra=extra,
                )
            else:
                put_status, body = fhir("POST", "/ActivityDefinition", payload)
            if put_status not in (200, 201) or not isinstance(body, dict):
                raise RuntimeError(
                    f"ActivityDefinition {meta['slug']} {put_status} {body}"
                )
            return body["id"]

        ad_id = retry(upsert)
        print(" ", meta["slug"], ad_id)
        created[meta["slug"]] = ad_id
        time.sleep(0.15)

    print(json.dumps(created, indent=2))
    print("waiting for stream")
    time.sleep(16)

    bq = bigquery.Client(project=PROJECT, credentials=creds)
    job_config = bigquery.QueryJobConfig(labels={"datacloud": "cursor"})
    print("collapse ActivityDefinition")
    bq.query(
        f"""
        CREATE OR REPLACE TABLE `{PROJECT}.synth_healthcare.ActivityDefinition` AS
        SELECT * FROM `{PROJECT}.synth_healthcare.ActivityDefinition`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY commitTimestamp DESC) = 1
        """,
        job_config=job_config,
    ).result()

    gap = list(
        bq.query(
            f"""
        WITH needed AS (
          SELECT DISTINCT SPLIT(leaf.definition.canonical, '|')[OFFSET(0)] AS url
          FROM `{PROJECT}.synth_healthcare.PlanDefinition` pd,
               UNNEST(pd.action) contact,
               UNNEST(contact.action) leaf
          WHERE pd.id = '{PLAN_ID}'
            AND leaf.definition.canonical IS NOT NULL
        )
        SELECT COUNT(*) AS n
        FROM needed
        WHERE NOT EXISTS (
          SELECT 1
          FROM `{PROJECT}.synth_healthcare.ActivityDefinition` ad
          WHERE ad.url = needed.url AND ad.status = 'active'
        )
        """,
            job_config=job_config,
        ).result()
    )
    print("plan actions missing ActivityDefinition", [dict(r) for r in gap])


if __name__ == "__main__":
    main()
