# Model Registry

Each model record tracks ID, version, parent, model type, base model, adapter, quantization, dataset/configuration, evaluation score, checkpoint and status.

Lifecycle: `candidate -> testing/approved -> current/production`, with `rejected` and `archived` retained for rollback. The existing `current` status is kept for compatibility; production semantics are represented by the deployed current model.
