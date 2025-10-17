# Barista Scheduler / Payouts

A small Flask app that reads Google Calendar events and computes base pay plus card-tip splits per day and per shift. This repo includes deployment scaffolding for GitHub-driven hosting.

## What kind of hosting fits?

- GitHub Pages cannot host this, because it's a dynamic Python/Flask app that needs server-side code and Google OAuth.
- Recommended: deploy a container to a managed host and trigger deploys from GitHub:
  - Google Cloud Run (fully managed, serverless, great for containers) — workflow provided.
  - Alternatives: Render, Railway, Fly.io — also work; steps below include a quick Render path.

## Deploy with Google Cloud Run (via GitHub Actions)

This repo contains:
- `barista-pay/Dockerfile` — builds a production image that runs `gunicorn app:app` on port 8080.
- `.github/workflows/deploy-cloud-run.yml` — a workflow that builds/pushes the image and deploys to Cloud Run when you push to `main`.

### Prereqs in Google Cloud
1. Create a GCP project and enable the APIs:
   - Cloud Run API
   - Artifact Registry API
   - Cloud Build API
2. Create a service account with the roles:
   - Cloud Run Admin
   - Artifact Registry Writer
   - Service Account Token Creator (for Workload Identity Federation)
3. Set up Workload Identity Federation for GitHub Actions:
   - Create a Workload Identity Pool & Provider (issuer: `https://token.actions.githubusercontent.com`).
   - Grant your service account `roles/iam.workloadIdentityUser` on that provider.
   - Note the provider resource name and the service account email.

### Configure GitHub Secrets
In your GitHub repo, add these secrets (Settings → Secrets and variables → Actions → New repository secret):
- `GCP_PROJECT_ID` — your GCP project ID
- `GCP_WIF_PROVIDER` — resource name of your WIF provider, e.g. `projects/123456789/locations/global/workloadIdentityPools/gh-pool/providers/gh-provider`
- `GCP_SERVICE_ACCOUNT` — service account email used by the workflow
- `CALENDAR_ID` — the Google Calendar ID to read from (e.g. `primary` or your calendar address)
- `SECRET_KEY` — Flask secret for sessions

Optional envs (can also be changed in the workflow):
- `TZ` (default `America/Chicago`)
- `OPEN_TIME` (default `08:00`)
- `SWITCH_TIME` (default `14:00`)
- `CLOSE_TIME` (default `21:00`)

### First-time OAuth tokens
This app uses Google OAuth Desktop credentials to access Calendar in read-only mode.
- `barista-pay/credentials.json` is referenced at runtime and should be provided securely.
- `barista-pay/token.json` will be created on first auth and cached for refresh.

For Cloud Run, you have two options:
1. Attach a volume or Secret containing `credentials.json` and mount it at runtime. Or
2. Bake `credentials.json` into the image only for your private repo (not recommended for public repos).

A safer approach is to create a Service Account key and use Service Account domain-wide delegation with Calendar API if applicable; however, this app currently uses the installed-app OAuth flow. If you deploy without an interactive browser, the new-token flow can fail. Workarounds:
- Generate `token.json` locally (run the app once on your machine), commit neither file, but store both `credentials.json` and `token.json` in a GCP Secret Manager and mount them as files to Cloud Run (requires minor code to read file paths from env vars).

> Note: `.dockerignore` already excludes `credentials.json` and `token.json` from the image by default.

### Deploy
Push to `main` or run the workflow manually (Actions → Deploy to Cloud Run). After deploy, the job prints the service URL.

## Optional: Firebase Hosting in front of Cloud Run

Use Firebase Hosting as a CDN/SSL edge and proxy all routes to your Cloud Run service.

Included files:
- `firebase.json` — rewrites everything to Cloud Run service `barista-pay` in region `us-central1`.
- `.firebaserc` — set `YOUR_FIREBASE_PROJECT_ID` to your project.
- `.github/workflows/deploy-firebase.yml` — deploys Hosting on push (requires a token).

Steps:
1. Create/choose a Firebase project linked to the same GCP project as Cloud Run.
2. Edit `.firebaserc` to set your project ID.
3. If your Cloud Run service name or region differ, update `firebase.json` accordingly.
4. Create GitHub secret `FIREBASE_TOKEN` (run `firebase login:ci` locally to generate).
5. Push to `main` to deploy Hosting. You can connect a custom domain in Firebase console.

Note: This does not replace Cloud Run; Hosting acts as a frontend proxy to your backend.

## Quick alternative: Render.com
1. Push this repo to GitHub.
2. Create a new Web Service in Render, connect the repo.
3. Build command:
   ```
   docker build -t app -f barista-pay/Dockerfile .
   ```
4. Start command (Render auto-runs the container CMD): uses `gunicorn -b 0.0.0.0:${PORT} app:app`.
5. Set environment variables: `CALENDAR_ID`, `SECRET_KEY`, `TZ`, `OPEN_TIME`, `SWITCH_TIME`, `CLOSE_TIME`.
6. Provide `credentials.json` and `token.json` via Render Disk or Secrets Files. If using Secrets Files, set env vars in code to point to their mounted paths or place them at `/app/credentials.json` and `/app/token.json`.

## Local development
- Create a virtualenv, install `requirements.txt` and set env vars if needed.
- Run the Flask app:
  ```
  python barista-pay/app.py
  ```
- Or containerized:
  ```
  docker build -t barista-pay -f barista-pay/Dockerfile .
  docker run -p 8080:8080 --env CALENDAR_ID=primary --env SECRET_KEY=dev --env TZ=America/Chicago \
    -v $(pwd)/barista-pay/credentials.json:/app/credentials.json \
    -v $(pwd)/barista-pay/token.json:/app/token.json \
    barista-pay
  ```

## Security notes
- Never commit `credentials.json` or `token.json` to a public repo. Use secret stores.
- Use private calendars or least-privileged access.
- Rotate tokens if leaked.
