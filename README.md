# OmniAI

OmniAI is a private, owner-controlled AI stack: Android client + FastAPI backend + SQLite + memory/RAG + model registry/checkpoints/rollback + training/evaluation + sandboxed tools + approval/audit controls.

## What is real

- Real LLM runtime: Hugging Face Transformers or GGUF via llama.cpp, loaded through `app/llm/engine.py`.
- NeuralCore remains as an optional classifier/router and CPU training reference; it is not the general chat generator when a real LLM is loaded.
- Chat history, multiple conversations, memory and RAG are persisted in SQLite.
- Tool Gateway is the only internal tool choke point.
- Network defaults OFF and uses owner allow/block policy.
- Sandbox executes Python/pytest with isolation and kill-switch monitoring.
- Coding Agent works in a separate Git workspace. Approved patches are validated, applied, tested and rolled back on failure.
- Replay, EWC and distillation are part of the existing NeuralCore training loop.
- Optional Transformers/PEFT LoRA/QLoRA pipeline is provided without forcing those heavy dependencies onto CPU-only installs.
- Candidate/stable evaluation gates remain in place.
- Owner sessions, encrypted Android storage, audit chain and kill switch are implemented.

## Tests

```bash
cd backend
pytest -q
```

Current repository test result after the implementation pass: **50 passed, 0 failed**. Three non-fatal warnings remain from the existing FastAPI startup event and PyTorch scalar conversion.

## Real LLM setup

```bash
cd backend
pip install -r requirements-llm.txt
```

Then call the owner-only `POST /api/v1/models/llm/load` with a Hugging Face model ID or a GGUF path. The runtime detects CPU/CUDA, reuses an already-loaded model and supports generation and streaming.

A model must actually exist and be compatible with the installed backend. This repository does not silently download or fabricate a model for tests.

## Training

The lightweight NeuralCore cycle is available on CPU. For a real language model use the optional PEFT pipeline in `app/training/hf_trainer.py`. QLoRA requires a supported CUDA/bitsandbytes environment.

## Security boundary

`Owner -> Policy -> Approval -> Agent -> Sandbox/Tools`.

The agent cannot grant itself permissions, change owner permissions, disable audit/kill switch, open network access or directly modify production code.

See `ARCHITECTURE.md`, `SECURITY.md`, `TRAINING.md`, `MODEL_REGISTRY.md`, `SELF_IMPROVEMENT.md`, `SANDBOX.md`, `API.md` and `DEPLOYMENT.md`.
