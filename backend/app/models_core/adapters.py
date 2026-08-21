"""Model adapter catalog.

This layer decouples registry metadata from the concrete runtime. A registry row
can describe a local NeuralCore checkpoint, a Hugging Face / PEFT model, or a
GGUF model served through llama.cpp. Training/orchestration code can inspect
adapter capabilities without hard-coding every model family in multiple places.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class AdapterDescriptor:
    key: str
    display_name: str
    model_type: str
    runtime: str
    checkpoint_kind: str
    supports_training: bool
    supports_inference: bool
    supports_quantization: bool


class BaseAdapter:
    descriptor: AdapterDescriptor

    def matches(self, model_row: dict[str, Any]) -> bool:
        raise NotImplementedError

    def describe(self, model_row: dict[str, Any]) -> dict[str, Any]:
        checkpoint = model_row.get("checkpoint_path")
        checkpoint_name = Path(checkpoint).name if checkpoint else None
        return {
            **asdict(self.descriptor),
            "checkpoint": checkpoint_name,
            "base_model": model_row.get("base_model"),
            "adapter_path": model_row.get("adapter"),
            "quantization": model_row.get("quantization"),
            "loaded_runtime": None,
        }


class NeuralCoreAdapter(BaseAdapter):
    descriptor = AdapterDescriptor(
        key="neuralcore",
        display_name="NeuralCore",
        model_type="neuralcore",
        runtime="pytorch-local",
        checkpoint_kind=".pt",
        supports_training=True,
        supports_inference=True,
        supports_quantization=False,
    )

    def matches(self, model_row: dict[str, Any]) -> bool:
        model_type = (model_row.get("model_type") or "").lower()
        checkpoint = (model_row.get("checkpoint_path") or "").lower()
        return model_type in ("", "neuralcore") or checkpoint.endswith(".pt")


class HuggingFaceAdapter(BaseAdapter):
    descriptor = AdapterDescriptor(
        key="huggingface",
        display_name="Hugging Face / PEFT",
        model_type="transformers",
        runtime="transformers",
        checkpoint_kind="directory-or-hf-ref",
        supports_training=True,
        supports_inference=True,
        supports_quantization=True,
    )

    def matches(self, model_row: dict[str, Any]) -> bool:
        model_type = (model_row.get("model_type") or "").lower()
        base_model = (model_row.get("base_model") or "").lower()
        adapter = (model_row.get("adapter") or "").lower()
        checkpoint = (model_row.get("checkpoint_path") or "").lower()
        return (
            model_type in ("hf", "transformers", "peft", "lora", "qlora")
            or "huggingface.co" in base_model
            or bool(adapter)
            or checkpoint.endswith(".safetensors")
        )


class GGUFAdapter(BaseAdapter):
    descriptor = AdapterDescriptor(
        key="gguf",
        display_name="GGUF / llama.cpp",
        model_type="gguf",
        runtime="llama.cpp",
        checkpoint_kind=".gguf",
        supports_training=False,
        supports_inference=True,
        supports_quantization=True,
    )

    def matches(self, model_row: dict[str, Any]) -> bool:
        model_type = (model_row.get("model_type") or "").lower()
        base_model = (model_row.get("base_model") or "").lower()
        checkpoint = (model_row.get("checkpoint_path") or "").lower()
        return model_type == "gguf" or base_model.endswith(".gguf") or checkpoint.endswith(".gguf")


class UnknownAdapter(BaseAdapter):
    descriptor = AdapterDescriptor(
        key="unknown",
        display_name="Unknown / external runtime",
        model_type="unknown",
        runtime="external",
        checkpoint_kind="unknown",
        supports_training=False,
        supports_inference=False,
        supports_quantization=False,
    )

    def matches(self, model_row: dict[str, Any]) -> bool:
        return True


_ADAPTERS: list[BaseAdapter] = [
    NeuralCoreAdapter(),
    HuggingFaceAdapter(),
    GGUFAdapter(),
    UnknownAdapter(),
]


def resolve_adapter(model_row: Optional[dict[str, Any]]) -> BaseAdapter:
    row = model_row or {}
    for adapter in _ADAPTERS:
        if adapter.matches(row):
            return adapter
    return UnknownAdapter()


def describe_model_adapter(model_row: Optional[dict[str, Any]]) -> dict[str, Any]:
    adapter = resolve_adapter(model_row)
    return adapter.describe(model_row or {})


def adapters_catalog() -> list[dict[str, Any]]:
    return [asdict(a.descriptor) for a in _ADAPTERS]
