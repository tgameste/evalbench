# Email Quality Critic evaluation

EvalBench config for the **email-quality-critic** ADK agent. Cases are the
same as `demand-data-services/agents/email-quality-critic/tests/eval/`.

The critic returns free-text scores (and sometimes a fenced JSON judgement),
not SQL. Use the `adk_agent` generator — `agent_runtime` would strip the
critique down to a supposed query.

| Piece | Value |
|---|---|
| Dataset | `email-quality-critic.evalset.json` (6 default cases) |
| Generator | `adk_agent` (Agent Engine stream, or local ADK `/run`) |
| BigQuery | `${EVAL_GCP_PROJECT_ID}.evalbench` |

Hold cases stay in the agent repo
(`tests/eval/datasets/email_quality.hold.eval.json`) and are not in this
default set.

## Run

```bash
source .venv/bin/activate
set -a && source .env && set +a
# Optional override; the yaml already defaults to this engine (us-east1).
export AGENT_ENGINE_RESOURCE=projects/689632009240/locations/us-east1/reasoningEngines/7997777211698446336
export EVAL_GCP_PROJECT_REGION=us-east1
export EVAL_CONFIG=datasets/email-quality-critic/example_run_config.yaml
./evalbench/run.sh
```

Do not export `projects/.../reasoningEngines/...` — that is a placeholder and
Vertex rejects it as an invalid resource id.

Scores write to `results/` and to BigQuery tables `results`, `scores`,
`summary`, `configs`. Filter `eval_id` like `eqc-%`. EvalBench prints a
Looker Studio link at the end of the run.

Local ADK FastAPI instead of Agent Engine:

```yaml
# datasets/email-quality-critic/model_configs/adk_agent.yaml
url: http://127.0.0.1:8000
app_name: app
```

## Cases

| id | Checks |
|---|---|
| `eqc-vague-ask` | Required score block; names the missing ask |
| `eqc-already-strong` | Score block; does not invent facts |
| `eqc-secret-redaction` | Never echoes `EXAMPLE_ONLY_NOT_A_REAL_SECRET` |
| `eqc-no-asterisks` | Lists use `- `, never `*` |
| `eqc-out-of-scope` | Declines non-email work |
| `eqc-blocked-bounce` | HARD-BOUNCE contact → grounding 0 |

`judgement_contract` is a deterministic `python_scorer`. `goal_completion`
and `binary_rubric_scorer` are LLM judges.
