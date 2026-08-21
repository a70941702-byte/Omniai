# Training

Two training paths exist:

1. The retained CPU NeuralCore path for lightweight intent learning, with Replay, EWC and distillation actually applied.
2. Optional Hugging Face/PEFT LoRA/QLoRA through `training/hf_trainer.py` for real causal language models.

Training data is provenance-bearing. Approved user corrections, verified datasets, teacher outputs, tool results and evaluation data can be accepted; model predictions are not automatically converted into labels.

Candidate models are evaluated before promotion. Stable/current remains intact until an owner-approved promotion succeeds. Regression, safety or no-gain decisions reject candidates.
