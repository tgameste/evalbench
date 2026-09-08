"""Attach observation-backed evidence to pregnancy-risk RiskAssessments."""

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
HTN_CONDITION = "e7f9d1e9-1c9c-4fa5-a574-537aed335419"

LOW_RATIONALE = (
    "Normotensive antenatal blood pressure and negative urine protein."
)
MOD_HTN_RATIONALE = (
    "Chronic hypertension with elevated antenatal blood pressure."
)
MOD_PROT_RATIONALE = (
    "Elevated antenatal blood pressure and proteinuria without severe features."
)
HIGH_RATIONALE = (
    "Severe-range blood pressure and heavy proteinuria consistent with high maternal risk."
)

PATIENTS = [
    {
        "pid": "74ee3ce8-e896-433b-bb89-43c8ad5b333a",
        "ra": "e5e4c8da-143e-4675-8d40-04e235a84052",
        "cp": "e7b5bdec-76e5-4d97-9725-a43c29978af1",
        "risk": "Moderate",
        "sbp": 148,
        "dbp": 92,
        "protein": 0,
        "bp_interp": "H",
        "prot_interp": "N",
        "rationale": MOD_HTN_RATIONALE,
        "condition": HTN_CONDITION,
    },
    {
        "pid": "9b553331-8f4a-43c1-b83f-55c6aa859de4",
        "ra": "1d507bc4-b7ce-4039-81bf-2c8fd2db2ed0",
        "cp": "386a9ae4-700d-4bbb-92d2-608e3e3e70ae",
        "risk": "Low",
        "sbp": 118,
        "dbp": 76,
        "protein": 0,
        "bp_interp": "N",
        "prot_interp": "N",
        "rationale": LOW_RATIONALE,
        "condition": None,
    },
    {
        "pid": "ac2deca4-3467-4fa2-bf84-ae74289ef331",
        "ra": "e71e4d4b-fc0d-4211-98a4-55ab3516076a",
        "cp": "d81645b6-8354-4cd5-9e4b-2fa552d910f7",
        "risk": "High",
        "sbp": 168,
        "dbp": 110,
        "protein": 300,
        "bp_interp": "HH",
        "prot_interp": "HH",
        "rationale": HIGH_RATIONALE,
        "condition": "create-eclampsia-history",
    },
    {
        "pid": "d4a31e4f-2c79-4a7f-845b-519ef3c1f511",
        "ra": "9c89eb86-6931-4219-8c2b-95260fe1387e",
        "cp": "aaa5d20e-41f7-498f-a509-f264d0878b2e",
        "risk": "Moderate",
        "sbp": 142,
        "dbp": 88,
        "protein": 30,
        "bp_interp": "H",
        "prot_interp": "H",
        "rationale": MOD_PROT_RATIONALE,
        "condition": None,
    },
    {
        "pid": "2bae212d-9da5-4b31-957f-86f058f84503",
        "ra": "975a1f0e-3ae5-4a0f-af17-daecdb29dd7e",
        "cp": "4612770b-5197-4578-a07a-9f2674cc66e3",
        "risk": "Low",
        "sbp": 116,
        "dbp": 74,
        "protein": 0,
        "bp_interp": "N",
        "prot_interp": "N",
        "rationale": LOW_RATIONALE,
        "condition": None,
    },
    {
        "pid": "e81035c5-f3fa-42ad-88a0-b58a1ea6c994",
        "ra": "5fb3ac84-af62-4f03-80d0-94ac4c7f839f",
        "cp": "c60df24d-6422-46b9-bad5-7f6fac9cc00b",
        "risk": "Low",
        "sbp": 120,
        "dbp": 78,
        "protein": 0,
        "bp_interp": "N",
        "prot_interp": "N",
        "rationale": LOW_RATIONALE,
        "condition": None,
    },
    {
        "pid": "7a1c7fda-6b1a-44ff-b694-08ac926564c1",
        "ra": "b9477cd4-69de-4e92-83a6-4483fcc7b382",
        "cp": "35dec952-71ca-48f4-87a3-a895221a28ef",
        "risk": "Low",
        "sbp": 114,
        "dbp": 72,
        "protein": 0,
        "bp_interp": "N",
        "prot_interp": "N",
        "rationale": LOW_RATIONALE,
        "condition": None,
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


def interp(code):
    display = {"N": "Normal", "H": "High", "HH": "Critical high"}[code]
    return [
        {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                    "code": code,
                    "display": display,
                }
            ],
            "text": display,
        }
    ]


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

    created = {}
    for row in PATIENTS:
        pid = row["pid"]
        print("==", pid, row["risk"])
        bp_ident = f"bp|{pid}"
        prot_ident = f"protein|{pid}"
        report_ident = f"report|{pid}"

        def make_bp(row=row, bp_ident=bp_ident, pid=pid):
            return upsert_observation(
                bp_ident,
                {
                    "resourceType": "Observation",
                    "status": "final",
                    "identifier": [
                        {"system": ID_SYSTEM, "value": bp_ident}
                    ],
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                    "code": "exam",
                                    "display": "Exam",
                                }
                            ],
                            "text": "risk-evidence",
                        }
                    ],
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "85354-9",
                                "display": "Blood pressure panel with all children optional",
                            }
                        ],
                        "text": "Pregnancy risk evidence",
                    },
                    "subject": {"reference": f"Patient/{pid}"},
                    "effectiveDateTime": "2026-06-15T00:00:00Z",
                    "interpretation": interp(row["bp_interp"]),
                    "component": [
                        {
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "8480-6",
                                        "display": "Systolic blood pressure",
                                    }
                                ],
                                "text": "Systolic blood pressure",
                            },
                            "valueQuantity": {
                                "value": row["sbp"],
                                "unit": "mmHg",
                                "system": "http://unitsofmeasure.org",
                                "code": "mm[Hg]",
                            },
                        },
                        {
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://loinc.org",
                                        "code": "8462-4",
                                        "display": "Diastolic blood pressure",
                                    }
                                ],
                                "text": "Diastolic blood pressure",
                            },
                            "valueQuantity": {
                                "value": row["dbp"],
                                "unit": "mmHg",
                                "system": "http://unitsofmeasure.org",
                                "code": "mm[Hg]",
                            },
                        },
                    ],
                    "note": [
                        {
                            "text": (
                                f"Supports Pregnancy Risk Classification = {row['risk']}"
                            )
                        }
                    ],
                },
            )

        def make_protein(row=row, prot_ident=prot_ident, pid=pid):
            return upsert_observation(
                prot_ident,
                {
                    "resourceType": "Observation",
                    "status": "final",
                    "identifier": [
                        {"system": ID_SYSTEM, "value": prot_ident}
                    ],
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                    "code": "laboratory",
                                    "display": "Laboratory",
                                }
                            ],
                            "text": "risk-evidence",
                        }
                    ],
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "5804-0",
                                "display": "Protein [Mass/volume] in Urine by Test strip",
                            }
                        ],
                        "text": "Pregnancy risk evidence",
                    },
                    "subject": {"reference": f"Patient/{pid}"},
                    "effectiveDateTime": "2026-06-15T00:00:00Z",
                    "valueQuantity": {
                        "value": row["protein"],
                        "unit": "mg/dL",
                        "system": "http://unitsofmeasure.org",
                        "code": "mg/dL",
                    },
                    "interpretation": interp(row["prot_interp"]),
                    "note": [
                        {
                            "text": (
                                f"Supports Pregnancy Risk Classification = {row['risk']}"
                            )
                        }
                    ],
                },
            )

        bp_id = retry(make_bp)
        prot_id = retry(make_protein)
        print("  obs", bp_id, prot_id)

        cond_id = row["condition"]
        if cond_id == "create-eclampsia-history":

            def make_eclampsia(pid=pid):
                existing = find_by_identifier("Condition", f"eclampsia|{pid}")
                if existing:
                    return existing["id"]
                body = {
                    "resourceType": "Condition",
                    "identifier": [
                        {"system": ID_SYSTEM, "value": f"eclampsia|{pid}"}
                    ],
                    "clinicalStatus": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                "code": "active",
                            }
                        ]
                    },
                    "verificationStatus": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                "code": "confirmed",
                            }
                        ]
                    },
                    "code": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "161811007",
                                "display": "History of eclampsia",
                            }
                        ],
                        "text": "History of eclampsia",
                    },
                    "subject": {"reference": f"Patient/{pid}"},
                    "recordedDate": "2026-06-15",
                }
                status, resp = fhir("POST", "/Condition", body)
                if status not in (200, 201) or not isinstance(resp, dict):
                    raise RuntimeError(f"Condition POST {status} {resp}")
                return resp["id"]

            cond_id = retry(make_eclampsia)
            print("  eclampsia", cond_id)

        def make_report(
            row=row,
            report_ident=report_ident,
            pid=pid,
            bp_id=bp_id,
            prot_id=prot_id,
        ):
            existing = find_by_identifier("DiagnosticReport", report_ident)
            body = {
                "resourceType": "DiagnosticReport",
                "identifier": [
                    {"system": ID_SYSTEM, "value": report_ident}
                ],
                "status": "final",
                "code": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": "57060-6",
                            "display": "Health assessment note",
                        }
                    ],
                    "text": "Pregnancy risk evidence panel",
                },
                "subject": {"reference": f"Patient/{pid}"},
                "effectiveDateTime": "2026-06-15T00:00:00Z",
                "result": [
                    {"reference": f"Observation/{bp_id}"},
                    {"reference": f"Observation/{prot_id}"},
                ],
                "conclusion": row["rationale"],
            }
            if existing:
                version = existing["meta"]["versionId"]
                updated = strip_meta(copy.deepcopy(existing))
                updated.update(body)
                updated["id"] = existing["id"]
                status, resp = fhir(
                    "PUT",
                    f"/DiagnosticReport/{existing['id']}",
                    updated,
                    extra={"If-Match": f'W/"{version}"'},
                )
                if status not in (200, 201) or not isinstance(resp, dict):
                    raise RuntimeError(f"DiagnosticReport PUT {status} {resp}")
                return resp["id"]
            status, resp = fhir("POST", "/DiagnosticReport", body)
            if status not in (200, 201) or not isinstance(resp, dict):
                raise RuntimeError(f"DiagnosticReport POST {status} {resp}")
            return resp["id"]

        report_id = retry(make_report)
        print("  report", report_id)

        def update_ra(
            row=row,
            bp_id=bp_id,
            prot_id=prot_id,
            report_id=report_id,
            cond_id=cond_id,
        ):
            status, resource = fhir("GET", f"/RiskAssessment/{row['ra']}")
            if status != 200 or not isinstance(resource, dict):
                raise RuntimeError(f"RiskAssessment GET {status} {resource}")
            version = resource["meta"]["versionId"]
            updated = strip_meta(copy.deepcopy(resource))
            preds = updated.get("prediction") or [{}]
            preds[0]["rationale"] = row["rationale"]
            preds[0]["qualitativeRisk"] = {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/risk-probability",
                        "code": row["risk"].lower(),
                        "display": row["risk"],
                    }
                ],
                "text": row["risk"],
            }
            updated["prediction"] = preds
            updated["method"] = {
                "coding": [
                    {
                        "system": "https://langcare.health/fhir/assessment-method",
                        "code": "pregnancy_risk_assessment",
                        "display": "LangCare pregnancy_risk_assessment",
                    }
                ],
                "text": "LangCare pregnancy_risk_assessment",
            }
            if row.get("cp"):
                updated["basedOn"] = {"reference": f"CarePlan/{row['cp']}"}
            basis = [
                {"reference": f"Observation/{bp_id}"},
                {"reference": f"Observation/{prot_id}"},
                {"reference": f"DiagnosticReport/{report_id}"},
            ]
            if cond_id:
                basis.append({"reference": f"Condition/{cond_id}"})
            updated["basis"] = basis
            put_status, put_body = fhir(
                "PUT",
                f"/RiskAssessment/{row['ra']}",
                updated,
                extra={"If-Match": f'W/"{version}"'},
            )
            if put_status not in (200, 201) or not isinstance(put_body, dict):
                raise RuntimeError(f"RiskAssessment PUT {put_status} {put_body}")
            return row["ra"]

        print("  ra", retry(update_ra))
        created[pid] = {
            "risk": row["risk"],
            "bp": bp_id,
            "protein": prot_id,
            "report": report_id,
            "condition": cond_id,
        }

    print(json.dumps(created, indent=2))
    print("waiting for stream")
    time.sleep(16)
    bq = bigquery.Client(project=PROJECT, credentials=creds)
    for table in (
        "Observation",
        "DiagnosticReport",
        "Condition",
        "RiskAssessment",
    ):
        print("collapse", table)
        bq.query(
            f"""
        CREATE OR REPLACE TABLE `{PROJECT}.synth_healthcare.{table}` AS
        SELECT * FROM `{PROJECT}.synth_healthcare.{table}`
        QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY commitTimestamp DESC) = 1
        """
        ).result()

    rows = list(
        bq.query(
            """
        SELECT ra.subject.patientId AS patient_id,
               ra.prediction[SAFE_OFFSET(0)].qualitativeRisk.text AS risk_level,
               ARRAY_LENGTH(ra.basis) AS basis_n,
               ra.prediction[SAFE_OFFSET(0)].rationale AS rationale
        FROM `mktg-vdc-poc-r83n.synth_healthcare.RiskAssessment` ra
        WHERE ra.code.coding[SAFE_OFFSET(0)].code = 'pregnancy-risk'
          AND ra.subject.patientId IN UNNEST([
            '74ee3ce8-e896-433b-bb89-43c8ad5b333a',
            '9b553331-8f4a-43c1-b83f-55c6aa859de4',
            'ac2deca4-3467-4fa2-bf84-ae74289ef331',
            'd4a31e4f-2c79-4a7f-845b-519ef3c1f511',
            '2bae212d-9da5-4b31-957f-86f058f84503',
            'e81035c5-f3fa-42ad-88a0-b58a1ea6c994',
            '7a1c7fda-6b1a-44ff-b694-08ac926564c1'
          ])
        ORDER BY patient_id
        """
        )
    )
    print(json.dumps([dict(r) for r in rows], indent=2))


if __name__ == "__main__":
    main()
