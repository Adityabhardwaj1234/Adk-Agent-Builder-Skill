# Deployment Guide (`docs/deployment.md`)

## Supported Deployment Targets

1. **Local Development (`local`)**:
   - Command: `adk web <project_dir>` or `adk run --state_file=state.json <project_dir>/app`
   - Smoke Test: `adk-agent-builder smoke-test --project-dir <project_dir>`
2. **Docker Container (`docker`)**:
   - Uses the generated non-root `Dockerfile` (`python:3.11-slim`, port `8080`, `USER 1000:1000`).
3. **Google Cloud Run (`cloud_run`)**:
   - Dry-Run Plan: `adk-agent-builder deploy --project-dir <dir> --target cloud_run --dry-run`
   - Rollback: `gcloud run services update-traffic <service> --to-revisions=PREVIOUS_REVISION=100 --region=<region>`
4. **Vertex AI Agent Runtime / Agent Engine (`agent_runtime`)**:
   - Supports dedicated custom service accounts (`--service-account`, added in ADK v2.12.0).
   - Dry-Run Plan: `adk-agent-builder deploy --project-dir <dir> --target agent_runtime --service-account sa@proj.iam.gserviceaccount.com --dry-run`
5. **Google Kubernetes Engine (`gke`)**:
   - Dry-Run Plan: `adk-agent-builder deploy --project-dir <dir> --target gke --dry-run`
   - Rollback: `kubectl rollout undo deployment/<project_name>`
