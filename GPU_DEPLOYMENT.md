# GPU Deployment

## Included assets
- `backend/Dockerfile.gpu` — CUDA/PyTorch backend image
- `backend/scripts/start_gpu_server.sh` — GPU container startup entrypoint
- `.github/workflows/docker-gpu-image.yml` — manual GHCR build/push workflow

## Recommended flow
1. Build and push the image from GitHub Actions, or locally:
   ```bash
   cd backend
   docker build -f Dockerfile.gpu -t omniai-backend:gpu .
   ```
2. In RunPod or Vast, create a pod from the pushed image.
3. Expose port `8000`.
4. Set environment variables:
   - `OMNI_OWNER_TOKEN`
   - optionally `OMNI_HOST=0.0.0.0`
   - optionally `OMNI_PORT=8000`
5. After startup:
   - check `/healthz`
   - check `/readyz`
   - authenticate through `/api/v1/auth/login`
   - enable `server_enabled` if desired
   - call `/api/v1/worker/start`

## Notes
- This image installs `requirements.txt` and `requirements-llm.txt`.
- Use persistent volume mounts if you want durable checkpoints and DB state.
- For production, place the backend behind HTTPS/TLS and restrict ingress to trusted clients.
