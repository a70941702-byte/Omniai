# API

Prefix: `/api/v1`

Core endpoints:
- `POST /auth/login`, `POST /auth/logout`
- `POST /chat`, `POST /chat/stream`
- `GET /conversations`, `/conversations/{id}/messages`
- `GET /models`, `/models/current`, `/models/runtime`
- `POST /models/llm/load`, `/models/llm/unload`, `/models/rollback`
- `GET /tools`, `POST /tools/call`
- `GET/POST /controls`
- `POST /kill-switch`
- `GET /worker/status`, `POST /worker/start`
- `POST /training/cycle`, `/training/start`, `/training/stop`
- `GET /evaluation/runs`, `/audit`, `/status`
- `GET/POST /approvals`, `/approvals/{id}/decide`, `/approvals/{id}/execute`
- `POST /sandbox/run`
- `POST /kb/ingest`, `GET /kb/search`
- memory and backup endpoints retained.
