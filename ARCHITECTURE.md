# OmniAI Architecture

Android is the owner client. FastAPI is the policy-enforcing API. The orchestrator combines a real LLM runtime (Transformers or GGUF/llama.cpp when installed), optional NeuralCore routing, conversation history, layered memory, RAG and Tool Gateway.

`Owner -> Policy -> Approval -> Agent -> Sandbox/Tools`

The LLM never receives a direct socket, shell, filesystem or provider credential. Tool calls pass through `ToolGateway`, which checks controls, kill switch, approval level and audit logging.

## Runtime
- `app/llm/engine.py`: real generative runtime, one loaded model at a time, CPU/CUDA detection, streaming.
- `app/models_core/neural_core.py`: retained as an optional classifier/router; never the primary generator.
- `app/tools/gateway.py`: unified calculator, Python/pytest, files, terminal, Git and web adapters.
- `app/security/policy.py`: capability and network policy.
- `app/sandbox/runner.py`: isolated subprocess execution.
- `app/training/hf_trainer.py`: optional Transformers + PEFT LoRA/QLoRA path.
- `app/workers/gpu_worker.py`: queued inference/training worker.
