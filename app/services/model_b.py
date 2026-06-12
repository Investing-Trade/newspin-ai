from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BIO_LABELS = ["O", "B", "I"]
POLARITIES_WITH_NONE = ["positive", "negative", "neutral", "none"]


def _require_ml_dependencies() -> tuple[Any, Any, Any, Any]:
    try:
        import torch
        from torch import nn
        from transformers import AutoConfig, AutoModel, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Local KoELECTRA inference requires torch and transformers. "
            "Install the ML dependencies or set MODE=gemini-api."
        ) from exc
    return torch, nn, AutoConfig, (AutoModel, AutoTokenizer)


def load_model_b_checkpoint(path: Path, config_source: Path, device: Any) -> tuple[Any, Any]:
    torch, nn, AutoConfig, auto_items = _require_ml_dependencies()
    AutoModel, AutoTokenizer = auto_items

    path = Path(path)
    with (path / "model_b_meta.json").open("r", encoding="utf-8") as f:
        meta = json.load(f)

    config = AutoConfig.from_pretrained(config_source)
    encoder = AutoModel.from_config(config)
    model = ModelBForABSA(
        encoder=encoder,
        hidden_size=int(config.hidden_size),
        nn_module=nn,
        loss_weights=meta.get("loss_weights"),
        bio_class_weights=meta.get("bio_class_weights"),
        polarity_label_smoothing=float(meta.get("polarity_label_smoothing", 0.0)),
    )
    state = torch.load(path / "model_state.pt", map_location=device)
    model.load_state_dict(state)
    model.to(device)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(path, use_fast=True)
    return model, tokenizer


class ModelBForABSA:
    def __new__(
        cls,
        encoder: Any,
        hidden_size: int,
        nn_module: Any,
        loss_weights: dict[str, float] | None = None,
        bio_class_weights: list[float] | None = None,
        polarity_label_smoothing: float = 0.0,
    ) -> Any:
        class _ModelBForABSA(nn_module.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = encoder
                self.dropout = nn_module.Dropout(getattr(encoder.config, "hidden_dropout_prob", 0.1))
                self.aspect_classifier = nn_module.Linear(hidden_size, len(BIO_LABELS))
                self.evidence_classifier = nn_module.Linear(hidden_size, len(BIO_LABELS))
                self.polarity_classifier = nn_module.Linear(hidden_size, len(POLARITIES_WITH_NONE))
                self.loss_weights = loss_weights or {"aspect": 1.0, "evidence": 1.0, "polarity": 1.0}
                self.bio_class_weights = bio_class_weights or [1.0, 1.0, 1.0]
                self.polarity_label_smoothing = polarity_label_smoothing

            def forward(
                self,
                input_ids: Any,
                attention_mask: Any,
                token_type_ids: Any | None = None,
                aspect_labels: Any | None = None,
                evidence_labels: Any | None = None,
                polarity_labels: Any | None = None,
            ) -> dict[str, Any]:
                kwargs = {"input_ids": input_ids, "attention_mask": attention_mask}
                if token_type_ids is not None:
                    kwargs["token_type_ids"] = token_type_ids
                outputs = self.encoder(**kwargs)
                sequence_output = self.dropout(outputs.last_hidden_state)
                cls_output = sequence_output[:, 0]
                aspect_logits = self.aspect_classifier(sequence_output)
                evidence_logits = self.evidence_classifier(sequence_output)
                polarity_logits = self.polarity_classifier(cls_output)
                return {
                    "loss": None,
                    "aspect_logits": aspect_logits,
                    "evidence_logits": evidence_logits,
                    "polarity_logits": polarity_logits,
                }

        return _ModelBForABSA()
