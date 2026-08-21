# Deployment

## Backend

### Local run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Public operational endpoints now include:
- `GET /healthz` → liveness probe
- `GET /readyz` → schema/readiness probe

Owner monitoring endpoints now include:
- `GET /api/v1/auth/me` → current session details and session policy
- `GET /api/v1/metrics` → JSON metrics snapshot
- `GET /api/v1/metrics/prometheus` → Prometheus-style text metrics

For a real local LLM install `requirements-llm.txt`, then load an HF model or GGUF path through the owner API.

### Docker

A production-oriented CPU container definition now exists at `backend/Dockerfile`.
A GPU-oriented image definition also exists at `backend/Dockerfile.gpu`.

```bash
cd backend
docker build -t omniai-backend .
docker run -e OMNI_OWNER_TOKEN=change-me -p 8000:8000 omniai-backend
```

### Render

A Render blueprint file now exists at `render.yaml`.
Set `OMNI_OWNER_TOKEN` in Render as a protected environment variable before deployment.

### GPU hosts (RunPod / Vast)

See `GPU_DEPLOYMENT.md` for the GPU image, startup flow, and GHCR build workflow.

## GPU worker

Run the backend on the GPU host, enable `server_enabled` and start `/api/v1/worker/start`. GPU detection is performed with PyTorch and jobs are queued instead of loading concurrent copies of the model.

## Android

Open `android/` in Android Studio. Release builds require HTTPS. Debug builds permit cleartext so an emulator can reach a development server. The Android client stores only the session token in AndroidX encrypted preferences; the owner secret is never embedded in the APK.

## CI / CD

GitHub Actions workflows now exist for:
- backend test + compile validation: `.github/workflows/backend-ci.yml`
- backend manual load profile: `.github/workflows/backend-load-test.yml`
- Android debug APK build + artifact upload: `.github/workflows/android-build.yml`
- Android release APK build + artifact upload: `.github/workflows/android-release.yml`
- GPU Docker image build/push: `.github/workflows/docker-gpu-image.yml`

The backend workflow now also runs a small concurrent smoke-load script after tests.
The manual load-test workflow runs a heavier async profile.
The Android debug workflow uploads `app-debug.apk` as a build artifact for each successful run.
The Android release workflow is manual (`workflow_dispatch`) and uploads `app-release.apk`.

## Monitoring

A starter Prometheus + Grafana stack now exists under `ops/monitoring/`.
See `ops/monitoring/README.md` for setup.
