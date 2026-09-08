# FHIR Data Agent evaluation

EvalBench config for the deployed **FHIR Data Agent** (Agent Engine) over the
LangCare demo FHIR store streamed to BigQuery (`synth_healthcare`, ANALYTICS_V2).

| Piece | Value |
|---|---|
| Agent Engine | `projects/mktg-vdc-poc-r83n/locations/us-central1/reasoningEngines/5634765645154353152` |
| GDA data agent | `projects/mktg-vdc-poc-r83n/locations/us/dataAgents/agent_eb1786f7-99d2-42ae-9022-f39ebb6fe19c` |
| FHIR store | `projects/mktg-vdc-poc-r83n/locations/us-west2/datasets/langcare-demo/fhirStores/demo-r4` |
| BigQuery dataset | `mktg-vdc-poc-r83n.synth_healthcare` |

The agent answers natural-language FHIR questions and returns generated SQL in a
` ```sql ` fence. EvalBench's `agent_runtime` generator extracts that SQL and
scores it against golden queries on BigQuery.

## Run

From the repo root, with the venv active and GCP env vars set:

```bash
source .venv/bin/activate
set -a && source .env && set +a
export EVAL_CONFIG=datasets/fhir-data-agent/example_run_config.yaml
./evalbench/run.sh
```

Scores are written locally under `results/` and uploaded to
`mktg-vdc-poc-r83n.evalbench` (tables `results`, `scores`, `summary`, `configs`).
EvalBench prints a Looker Studio link at the end of the run.

Override the engine without editing YAML:

```bash
export AGENT_ENGINE_RESOURCE=projects/mktg-vdc-poc-r83n/locations/us-central1/reasoningEngines/5634765645154353152
```

## Dataset

`prompts.json` has four layers:

- **Population DQL** — resource counts, gender/status breakdowns, Observation filters
- **Patient-specific DQL** — Patient/74ee3ce8-e896-433b-bb89-43c8ad5b333a and her
  active antenatal CarePlan/e7b5bdec-76e5-4d97-9725-a43c29978af1, plus pregnancy
  and WHO CarePlan checks for additional demo patients
- **Maternal education DQL** — every pregnant patient is on a CarePlan; each plan
  has major goals, education sub-goals, patient-action activities with a golden
  URL, and a completed notification Task
- **PRAMS questionnaire DQL** — every pregnant patient has completed the CDC
  PRAMS Phase 9.2 Core Questionnaire (`Questionnaire/1eb98103-88ef-411c-8d5b-1dce22f6dbd5`)
- **WHO ActivityDefinition DQL** — every leaf on `PlanDefinition/who-anc8` has a
  matching patient-independent ActivityDefinition template
- **Research study DQL** — every pregnant patient is an on-study ResearchSubject
  on `ResearchStudy/e7e8ae43-a33e-45c2-a0e3-be909d319ff9` with research Consent
  and membership on `Group/586f5f4c-9b36-496e-b0a9-380f5a121f4c`
- **Study-goal DQL** — enrolled patients have both major goals; education
  sub-goals `partOf` those goals; activity completions are process proxies
  (they do not themselves equal mortality reduction)

Re-seed or collapse after FHIR writes with:

```bash
python datasets/fhir-data-agent/seed_maternal_education.py
python datasets/fhir-data-agent/seed_prams_questionnaire.py
python datasets/fhir-data-agent/seed_who_activity_definitions.py
python datasets/fhir-data-agent/seed_maternal_study_protocol.py
python datasets/fhir-data-agent/seed_maternal_study_enrollment.py
python datasets/fhir-data-agent/seed_cpg_careplan_apply.py
```

Every patient with an active Normal pregnancy Condition (SNOMED `72892002`) has
an **active** CarePlan. CarePlans carry two **major goals** and two education
**sub-goals**:

| Kind | `Goal.category[0].text` | Description |
|---|---|---|
| Major | `major-goal` | Maternal Health Mortality Reduction |
| Major | `major-goal` | Neonatal / Fetal Co-morbidity Reduction |
| Sub-goal | `sub-goal` | Complete assigned maternal education resource (`note` = `partOf: Goal/{parent}`) |
| Sub-goal | `sub-goal` | Complete assigned neonatal education resource (`note` = `partOf: Goal/{parent}`) |

Golden maternal education URLs are keyed by pregnancy risk and specific
condition. Neonatal education is the same URL for every pregnant patient.

| Risk / specific condition | Maternal URL |
|---|---|
| Low + SNOMED `72892002` | `https://www.cdc.gov/pregnancy/during/index.html` |
| Moderate, or HTN SNOMED `59621000` | `https://www.cdc.gov/hearher/maternal-warning-signs/index.html` |
| High | `https://www.cdc.gov/hearher/index.html` |
| Neonatal (all) | `https://www.cdc.gov/maternal-infant-health/infant-health/index.html` |

The URL is stored in three queryable places: `DocumentReference` (`type.text` =
`Pregnancy education resource`), `CarePlan.activity.detail.instantiatesUri` on
the `Patient action: review … education resource` activity, and `Task.instantiatesUri`
where `code.text` = `Education resource access` and `status` = `completed`
(patient notified; access marked complete).

Every pregnant patient is on an active **WHO ANC8** CarePlan
(`PlanDefinition/who-anc8`). Every patient on that CarePlan has an **AI**
`RiskAssessment`: `code=pregnancy-risk` and
`method.coding[0].code = pregnancy_risk_assessment`
(`method.text` = `LangCare pregnancy_risk_assessment`). The AI agent is
Device/`047e7ca5-9515-438c-8b0e-0fd169622799`.

The agent has a required input panel on every WHO patient (any Observation with
these LOINC codes):

| LOINC | Input |
|---|---|
| `85354-9` | Blood pressure |
| `5804-0` | Urine protein |
| `82810-3` | Pregnancy status |
| `11881-0` | Gestational age (weeks) |
| `39156-5` | BMI |
| `2345-7` | Serum glucose |
| `72166-2` | Tobacco smoking status |

Missing gestational-age (and a few 2bae212d… labs) were seeded as
`category.text = 'pra-input'`. Re-seed with
`python datasets/fhir-data-agent/seed_ai_pra.py`.

Every pregnant patient has a **completed** CDC PRAMS Phase 9.2 Core
`QuestionnaireResponse` (`questionnaire` =
`Questionnaire/1eb98103-88ef-411c-8d5b-1dce22f6dbd5`). Leaf answers are
flattened under the four section items so ANALYTICS_V2 can query them (the
stream keeps two `item` levels). Key grounded answers:

| linkId | Meaning | Value |
|---|---|---|
| `core-3-b` | Hypertension before pregnancy | `true` only for `74ee3ce8-…` (HTN `59621000`) |
| `core-10` | Received prenatal care | `true` (all on WHO ANC8) |
| `core-15-b` | Pregnancy HTN / preeclampsia / eclampsia | `true` only for high-risk `ac2deca4-…` |
| `core-17` / `core-18-c` | Maternal warning signs / Hear Her | `true` for Moderate and High |
| `core-41` | Current pregnancy-prevention status | `pregnant` for all seven |

Each WHO CarePlan also has a completed patient-action
`Patient action: complete the CDC PRAMS Phase 9.2 Core Questionnaire` and a
Task (`code.text` = `PRAMS questionnaire completion`) whose `focus` is the
QuestionnaireResponse. Re-seed with
`python datasets/fhir-data-agent/seed_prams_questionnaire.py`.

Every leaf action on `PlanDefinition/who-anc8` now has a matching
**ActivityDefinition** (43 canonicals). These are patient-independent
templates in the HL7 definitional pattern: `kind` (request type), SNOMED
`code`, `intent=proposal`, `priority`, `subject=Patient`, `participant.type`
+ role, `jurisdiction=US`, `topic`, `useContext` (pregnancy / user / outpatient
venue), and `timingTiming` with CQL `Now()` for apply-time. Medication-like
actions also carry `productCodeableConcept`. Re-seed with
`python datasets/fhir-data-agent/seed_who_activity_definitions.py`.

The store has no `$apply`. A first CPG CarePlan slice is applied in software
for Patient/`74ee3ce8-…` / CarePlan/`e7b5bdec-…`: `practice-blood-pressure`
becomes a `ServiceRequest` (`intent=proposal`, `instantiatesCanonical` = the
AD) and `practice-warning-signs` becomes a `CommunicationRequest` (R4 has no
`intent`; status `active` is the proposal).
Both are `basedOn` the CarePlan and listed as `activity.reference` only
(FHIR `cpl-3`: no inline `detail` on those activities). Re-seed with
`python datasets/fhir-data-agent/seed_cpg_careplan_apply.py`.

R5-only elements (`versionAlgorithm`, `asNeeded`, `participant.function`) are
omitted because `demo-r4` is FHIR R4.

Pregnancy-risk classifications are **evidence-based**. Each `RiskAssessment`
(`code=pregnancy-risk`) has `prediction.rationale` plus `basis` references to:

- a blood-pressure Observation (LOINC `85354-9`, category text `risk-evidence`)
- a urine-protein Observation (LOINC `5804-0`, category text `risk-evidence`)
- a `DiagnosticReport` (`code.text` = `Pregnancy risk evidence panel`) whose
  `result[]` points at those Observations and whose `conclusion` repeats the rationale
- a supporting Condition when applicable (essential hypertension `59621000` or
  history of eclampsia `161811007`)

| Risk | Supporting results |
|---|---|
| Low | BP ~114–120 / 72–78 (interp `N`), urine protein 0 (interp `N`) |
| Moderate + HTN | BP 148/92 (interp `H`), protein 0; Condition `59621000` |
| Moderate | BP 142/88 (interp `H`), urine protein 30 (interp `H`) |
| High | BP 168/110 (interp `HH`), urine protein 300 (interp `HH`); history of eclampsia |

Re-seed evidence with `python datasets/fhir-data-agent/seed_risk_evidence.py`.

| Patient | Risk | Specific | Active pregnancy Condition | Active CarePlan | Maternal URL |
|---|---|---|---|---|---|
| `74ee3ce8-e896-433b-bb89-43c8ad5b333a` | Moderate | HTN `59621000` | `39506ae8-daad-4afe-9f68-d772d53acd33` | `e7b5bdec-76e5-4d97-9725-a43c29978af1` | HEAR HER warning signs |
| `9b553331-8f4a-43c1-b83f-55c6aa859de4` | Low | `72892002` | `650d96fc-9ee4-4019-9c6d-648e225681b5` | `386a9ae4-700d-4bbb-92d2-608e3e3e70ae` | CDC pregnancy during |
| `ac2deca4-3467-4fa2-bf84-ae74289ef331` | High | `72892002` | `531a95c1-89d9-4a67-955c-d9a0a7a126b0` | `d81645b6-8354-4cd5-9e4b-2fa552d910f7` | HEAR HER hub |
| `d4a31e4f-2c79-4a7f-845b-519ef3c1f511` | Moderate | `72892002` | `4dbd1161-9806-43a0-9aa5-2db5f9591b6e` | `aaa5d20e-41f7-498f-a509-f264d0878b2e` | HEAR HER warning signs |
| `2bae212d-9da5-4b31-957f-86f058f84503` | Low | `72892002` | `9dacfb25-78f1-4ffc-a084-ce02d2092b24` | `4612770b-5197-4578-a07a-9f2674cc66e3` | CDC pregnancy during |
| `e81035c5-f3fa-42ad-88a0-b58a1ea6c994` | Low | `72892002` | `67a33a30-7e95-46de-997b-08334edb66dc` | `c60df24d-6422-46b9-bad5-7f6fac9cc00b` | CDC pregnancy during |
| `7a1c7fda-6b1a-44ff-b694-08ac926564c1` | Low | `72892002` | `4db28a4e-81e1-4588-a4e8-79195b11c4e5` | `35dec952-71ca-48f4-87a3-a895221a28ef` | CDC pregnancy during |

Patient `74ee3ce8-…` Pregnancy Risk Classification is **Moderate since 2025-05-10**,
stored as RiskAssessment/e5e4c8da-143e-4675-8d40-04e235a84052 (`code=pregnancy-risk`).

Existing routine antenatal CarePlans were updated in `demo-r4` to instantiate
`PlanDefinition/who-anc8`. Patient `7a1c7fda-…` did not have a CarePlan; one was
created so every pregnant patient is covered.

Each WHO CarePlan is now linked on the FHIR graph used by ANALYTICS_V2:

- `CarePlan.goal[].goalId` → `Goal.id` (new Goal: complete the WHO 8-contact pathway)
- `CarePlan.careTeam[].careTeamId` → `CareTeam.id` (already active, 3 participants)
- `CarePlan.activity[]` includes a `Task` whose description starts with `Patient action:` and whose performer is the same Patient as `subject.patientId`

| Patient | WHO Goal | CareTeam |
|---|---|---|
| `74ee3ce8-e896-433b-bb89-43c8ad5b333a` | `fafe0a84-ae75-4baa-8701-f973535e5a27` | `3dfb7da0-7634-41b2-8591-dfceffa0d209` |
| `9b553331-8f4a-43c1-b83f-55c6aa859de4` | `b603e274-3e90-436c-9988-fd85695e7f31` | `7440bc3a-e5c1-4bc5-81fb-dbeaa0afad13` |
| `ac2deca4-3467-4fa2-bf84-ae74289ef331` | `953d65ee-65e2-4b53-b265-7df08fae8206` | `95702bdf-6b96-4988-9da0-67161063e1b4` |
| `d4a31e4f-2c79-4a7f-845b-519ef3c1f511` | `cd938926-5ccb-430c-aaff-557efd661d21` | `867cf381-a300-4288-b386-199dd5a70ed4` |

`synth_healthcare` is a **current-state snapshot** for scoring: CarePlan and
RiskAssessment keep one row per `id` (latest `commitTimestamp`), and resolved
prior-pregnancy Conditions were removed for the four antenatal demo patients so
"is she pregnant?" is not drowned out by Synthea history. FHIR DELETE of those
Conditions returned 409 (still referenced), so they remain in `demo-r4` only.

Expected values against that snapshot:

| Prompt | Result |
|---|---|
| Patients | 10 |
| Observations | 3217 |
| Encounters | 690 |
| Conditions | 341 |
| Procedures | 1975 |
| Immunizations | 390 |
| Patients by gender | female 9, male 1 |
| Encounters by status | finished 688, planned 2 |
| Final observations | 3217 |
| Heart-rate observations | 235 |
| Patient gender | female |
| Patient observations | 577 |
| Patient encounters | 150 |
| Patient conditions | 84 |
| Patient unique CarePlans | 11 |
| Patient unique active CarePlans | 3 |
| CarePlan e7b5bdec… status | active |
| Has that active CarePlan | id + `active` |
| CarePlan description | WHO 8-contact antenatal pathway |
| Pregnancy risk class | Moderate |
| Pregnancy risk since | 2025-05-10 |
| 9b553331 / ac2deca4 / d4a31e4f pregnant | matching Condition id + `active` |
| 9b553331 / ac2deca4 / d4a31e4f WHO CarePlan | matching CarePlan id + `active` + WHO 8-contact description |
| WHO CarePlans → Goals | 35 rows (`goal[].goalId` = `Goal.id`, including major/sub/WHO goals) |
| High-risk CarePlan `88b1a0f4…` → Goals | 4 existing Goal texts |
| WHO CarePlans → CareTeams | 7 active teams, 3 participants each |
| WHO CarePlan patient-action activities | description starts with `Patient action:`, performer = subject |
| CarePlan `e7b5bdec…` Goals | 5 rows (WHO pathway + 2 major + 2 education sub-goals) |
| CarePlan `e7b5bdec…` CareTeam | `3dfb7da0-7634-41b2-8591-dfceffa0d209`, active, 3 participants |
| CarePlan `e7b5bdec…` patient action | antenatal education Task, maternal/neonatal education review, and PRAMS questionnaire |
| Pregnant patients missing an active CarePlan | 0 |
| Active CarePlan major goals | 14 rows (7 patients × 2 major goals) |
| Education sub-goals | 14 rows (`partOf: Goal/{major}`) |
| Pregnancy education DocumentReference URLs | 7 patients, catalog above |
| Education URL by risk | same 7 patients; risk text matches catalog |
| Education patient-action activities | 14 rows (maternal + neonatal review) |
| Education access Tasks | 7 completed (`Education resource access`) |
| Patient `74ee3ce8…` education URL | `https://www.cdc.gov/hearher/maternal-warning-signs/index.html` |
| Pregnancy-risk assessments with Observation basis | 7 patients; gap count 0 |
| Risk-evidence Observations | 14 (BP + urine protein per patient) |
| Risk-evidence DiagnosticReports | 7; each links 2 Observations |
| Patient `74ee3ce8…` evidence BP | systolic 148 / diastolic 92 (LOINC 8480-6 / 8462-4) |
| Patient `ac2deca4…` evidence protein | 300 mg/dL, interp `HH` |
| Pregnant patients missing WHO ANC8 CarePlan | 0 |
| WHO ANC8 patients missing AI pregnancy-risk RA | 0 |
| WHO patients missing any PRA input LOINC | 0 |
| AI pregnancy-risk RAs without rationale or Observation basis | 0 |
| Pregnant patients missing a completed PRAMS QuestionnaireResponse | 0 |
| Completed PRAMS responses | 7 (`status=completed`, questionnaire `Questionnaire/1eb98103-…`) |
| PRAMS `core-41` = pregnant | 7 |
| Patient `74ee3ce8…` PRAMS `core-3-b` (pre-pregnancy HTN) | `true` |
| WHO ANC8 CarePlans missing PRAMS patient-action | 0 |
| ResearchStudy protocol | `PlanDefinition` url `…/maternal-health-study-protocol` (8 ANC contacts + monitoring + escalation) |
| Pregnant patients missing an on-study ResearchSubject | 0 |
| On-study ResearchSubjects | 7 (`status=on-study`, arm `FHIR Coordinated Maternal Care`) |
| Enrolled missing Maternal Health Mortality Reduction goal | 0 |
| Enrolled missing Neonatal / Fetal Co-morbidity Reduction goal | 0 |
| Mortality major goal → maternal education sub-goal (`partOf`) | 7 |
| Neonatal major goal → neonatal education sub-goal (`partOf`) | 7 |
| Completed patient-action activities with empty `activity.detail.goal` | 21 |
| Enrolled missing completed maternal-education CarePlan activity | 0 |
| Enrolled missing completed `Education resource access` Task | 0 |
| Enrolled with fewer than 4 prenatal Encounters (SNOMED `424619006` / `424441002`) | 1 (`2bae212d-…`) |
| WHO ANC8 leaf actions missing an ActivityDefinition.url | 0 |
| WHO ANC8 ActivityDefinition templates | 43 (`kind` + `intent` + `participant.type`) |
| `practice-blood-pressure` | ServiceRequest / proposal / SNOMED `75367002` / practitioner |
| CPG apply (Hedwig CarePlan `e7b5bdec…`) | ServiceRequest proposal from `practice-blood-pressure`; CommunicationRequest proposal from `practice-warning-signs`; both hung as `activity.reference` |
