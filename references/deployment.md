# Deployment: Cloud Run, Agent Engine, Docker, GKE (ADK 2.x, Python)

Read this when the user asks to "deploy", "host", "publish" or "put it
online". `scripts/deploy_agent.py` implements the workflow below; this
document is the reasoning behind it and the manual fallback.

## Contents
1. Choosing a target
2. Preconditions (the part that wastes afternoons)
3. Cloud Run walkthrough
4. Agent Engine walkthrough
5. Docker and GKE
6. Secrets
7. Verify a deployment - a deploy is not done until a request succeeds
8. Rollback and redeploy
9. Cost notes

---

## 1. Choosing a target

| Target | Use when | Trade-off |
|---|---|---|
| `cloud_run` | Default for a user-facing or HTTP API deployment; scales to zero | You manage GCP project/region; cold starts |
| `agent_engine` | You want Google-managed agent hosting, sessions and scaling; Gemini Enterprise / Vertex setups | Requires project/region (or express-mode key); managed runtime |
| `docker` | You want the image locally (inspect, push to your own registry, run anywhere) | You still need infrastructure to host it |
| `gke` | The organisation already runs GKE and wants everything on-cluster | Most setup; choose it for policy, not preference |

If the user has no Google Cloud project, Cloud Run via a personal project is
the shortest useful path; Agent Engine is right when they are already on
Vertex/Enterprise. Ask before creating anything billable.

## 2. Preconditions

Cloud Run and Agent Engine both deploy through `gcloud`:

```bash
gcloud --version                 # SDK installed?
gcloud auth login                # user credentials
gcloud auth application-default login   # ADC for libraries
gcloud config get-value project
```

- a project with **billing enabled**;
- a region (`us-central1` is the common default);
- the deployer names any missing API on first run (`run.googleapis.com`,
  `aiplatform.googleapis.com`, ...) - enable it and re-run; this is normal,
  not an error in the agent.

`scripts/deploy_agent.py` runs these checks first and refuses plainly: a
missing `gcloud` fails fast instead of five minutes into a build.

## 3. Cloud Run walkthrough

The ADK command (verified flags, ADK 2.12):

```bash
adk deploy cloud_run \
    --project=my-project --region=us-central1 \
    --service_name=my-agent-service \
    --app_name=my_app \
    --with_ui \
    --env GOOGLE_GENAI_USE_ENTERPRISE=0 \
    ./workspace/my_app \
    -- --no-allow-unauthenticated        # extra flags after `--` go to gcloud
```

- `--with_ui` also serves the ADK Web UI at the service URL (great for
  demos; drop it for a pure API).
- Environment variables: repeat `--env K=V`.
- Anything after `--` is passed through to the provider tool (gcloud) - e.g.
  `-- --set-secrets=GOOGLE_API_KEY=my-key:latest` for Secret Manager,
  `-- --min-instances=0 --max-instances=5 --memory=1Gi` for sizing.
- ADK stages the **app folder as the source**; the build happens in the
  cloud. First deploys take several minutes.

With the script:

```bash
python scripts/deploy_agent.py ./workspace/my_app --mode cloud_run \
    --project my-project --region us-central1 --service-name my-agent-service \
    --env GOOGLE_GENAI_USE_ENTERPRISE=0 --dry-run      # always look first
python scripts/deploy_agent.py ./workspace/my_app --mode cloud_run \
    --project my-project --region us-central1 --service-name my-agent-service \
    --env GOOGLE_GENAI_USE_ENTERPRISE=0
```

It audits the app's `.env` for live-looking secrets before staging (see
section 6), prints the exact command, and writes
`<workspace>/adk_runs/deploy_report.json` with the outcome.

## 4. Agent Engine walkthrough

```bash
adk deploy agent_engine \
    --project=my-project --region=us-central1 \
    --display_name="Support Desk Agent" \
    --description="Handles customer support requests" \
    ./workspace/my_app
```

- Updating an existing deployment: pass `--agent_engine_id=<id>` (the id of
  the reasoning engine to update instead of creating a new one).
- Express mode (no project setup, API-key based):
  `adk deploy agent_engine --api_key=$GOOGLE_API_KEY ./workspace/my_app` -
  good for quick trials; not the path for production data.
- The command prints the deployed resource name/id; keep it (the deploy
  report stores it too).

Same script:

```bash
python scripts/deploy_agent.py ./workspace/my_app --mode agent_engine \
    --project my-project --region us-central1 \
    --display-name "Support Desk Agent" --api-key "$GOOGLE_API_KEY"
```

## 5. Docker and GKE

- `adk deploy docker ./workspace/my_app` builds the container image locally -
  use it to inspect the staged source or to run the agent anywhere Docker
  runs (`docker run -p 8000:8000 -e GOOGLE_API_KEY=... <image>`). Never bake a
  key into an image; pass it at run time.
- `adk deploy gke --project=... --region=... ./workspace/my_app` deploys to a
  Kubernetes cluster (for organisations that require it). Preconditions are a
  real cluster plus kubectl context; treat it as an infrastructure task, not a
  chat step.

## 6. Secrets

Three rules, in order of preference:

1. **Deployment env vars**: `--env GOOGLE_API_KEY=<real key>` at deploy time,
   sourced from the user's environment - nothing secret is stored in the
   repo.
2. **Secret Manager**: `-- --set-secrets=GOOGLE_API_KEY=my-key:latest` (Cloud
   Run). The container reads it as an env var like any other.
3. Local `.env` only for local runs. Deploys stage the app folder as source,
   so a live key in `.env` rides along with it unless the platform strips it.
   `scripts/deploy_agent.py` warns on exactly this pattern before anything is
   uploaded - keep the warning in mind when deploying by hand.

Also: the generated project `.gitignore`s `.env`; keep it that way, and never
echo a key into logs, state or the deploy report.

## 7. Verify a deployment

A deploy that printed "done" is not a deploy that works. Verify in this
order and stop at the first failure:

1. **Service answers**: for Cloud Run,
   `gcloud run services describe <service> --region <r> --format='value(status.url)'`
   then `curl <url>/health` and `curl <url>/list-apps` - the app name must
   appear.
2. **A real request succeeds**: the same suite that proved the agent locally
   can prove the deployed one, because `testing.py` speaks the same HTTP API:

   ```bash
   python scripts/testing.py --app my_app --base-url https://<service-url> \
       --workspace ./workspace --spec ./workspace/adk_runs/spec.json \
       --min-interval 2
   ```

   (In `--base-url` mode the spec runs against the remote service; pass
   `--server-log` only if you have the server's log locally - against a cloud
   URL you usually do not, which just means quota reclassification is
   unavailable; pace with `--min-interval` instead.)

   For Agent Engine, verify through its console/SDK surface or by exposing a
   thin HTTP layer; the smoke test idea is the same - one real conversation.
3. **Logs read clean**: Cloud Run logs (`gcloud run services logs read
   <service>`) show no import warnings or tracebacks at startup.
4. Record the outcome: URL, service name, engine id, and the verification
   result in the workspace (`adk_runs/deploy_report.json` plus a line in
   `evaluation.md`).

## 8. Rollback and redeploy

- **Cloud Run**: every deploy creates a revision. Roll traffic back with
  `gcloud run services update-traffic <service> --to-revisions=<rev>=100`
  (or shift percentages for a canary). Redeploy = run the same command again.
- **Agent Engine**: update the existing engine with `--agent_engine_id` to
  create a new version of it; keep the id so updates are explicit rather than
  accidental duplicates.
- After any rollback, re-run the verification request - a rollback that is
  not verified is a guess.

## 9. Cost notes

- Cloud Run scales to zero; you pay per request/CPU-second. Pilot deployments
  with default settings are typically cents, but a `--with_ui` demo left
  public will get crawled - protect it (`--no-allow-unauthenticated` plus IAM,
  or delete it).
- Agent Engine is managed hosting; it bills for the runtime, not per request.
  Delete trial engines when done.
- Free-tier API keys remain rate-limited in the cloud exactly as they are
  locally - a deployed agent with a free key is still a rate-limited agent.
  The deploy script's dry run is free; say what a real deploy will create
  before running it.
