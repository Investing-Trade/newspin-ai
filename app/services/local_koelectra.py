from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.config import Settings
from app.schemas import ArticleInput, OpinionResponse, SnippetResponse, SpanResponse
from app.services.inference import InferenceProvider
from app.services.model_b import POLARITIES_WITH_NONE, load_model_b_checkpoint
from app.services.snippet import SnippetCandidate
from app.services.span_decode import decode_bio_spans


class LocalModelError(RuntimeError):
    pass


class LocalKoELECTRAInferenceProvider(InferenceProvider):
    mode = "local-koelectra"
    local_model = True
    model_loaded = False

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model_version = settings.model_version
        self.model_a_dir = settings.resolved_model_a_path
        self.model_b_dir = settings.resolved_model_b_path
        self.package_dir = Path(settings.model_package_path)

        self._load_json_config()
        self._load_ml_dependencies()
        self._load_models()
        self.model_loaded = True

    def _load_json_config(self) -> None:
        for path in [
            self.model_a_dir,
            self.model_b_dir,
            self.package_dir / "label_map.json",
            self.package_dir / "thresholds.json",
            self.package_dir / "inference_config.json",
        ]:
            if not Path(path).exists():
                raise LocalModelError(f"Required local model path does not exist: {path}")

        self.label_map = self._read_json(self.package_dir / "label_map.json")
        self.thresholds = self._read_json(self.package_dir / "thresholds.json")
        self.inference_config = self._read_json(self.package_dir / "inference_config.json")
        self.categories: list[str] = [
            label
            for _, label in sorted(
                self.label_map["category_id2label"].items(),
                key=lambda item: int(item[0]),
            )
        ]
        self.category_thresholds: dict[str, float] = {
            str(category): float(value)
            for category, value in self.thresholds["model_a_category_thresholds"].items()
        }
        self.none_margins: dict[str, float] = {
            str(category): float(value)
            for category, value in self.thresholds["model_b_none_margin_by_category"].items()
        }
        tokenization = self.inference_config.get("tokenization", {})
        self.model_a_max_length = int(tokenization.get("model_a_max_length", 192))
        self.model_b_max_length = int(tokenization.get("model_b_max_length", 192))

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _load_ml_dependencies(self) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise LocalModelError(
                "Local KoELECTRA inference requires torch, transformers, safetensors, numpy, and tokenizers. "
                "Install the ML dependencies or set MODE=gemini-api."
            ) from exc

        self.torch = torch
        self.AutoModelForSequenceClassification = AutoModelForSequenceClassification
        self.AutoTokenizer = AutoTokenizer
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _load_models(self) -> None:
        self.model_a_tokenizer = self.AutoTokenizer.from_pretrained(self.model_a_dir, use_fast=True)
        self.model_a = self.AutoModelForSequenceClassification.from_pretrained(self.model_a_dir)
        self.model_a.to(self.device)
        self.model_a.eval()

        self.model_b, self.model_b_tokenizer = load_model_b_checkpoint(
            path=self.model_b_dir,
            config_source=self.model_a_dir,
            device=self.device,
        )

    async def analyze(
        self,
        article: ArticleInput,
        snippets: list[SnippetCandidate],
        include_raw_model_output: bool,
    ) -> list[SnippetResponse]:
        if not snippets:
            return []
        return await asyncio.to_thread(self._analyze_sync, snippets, include_raw_model_output)

    def _analyze_sync(
        self,
        snippets: list[SnippetCandidate],
        include_raw_model_output: bool,
    ) -> list[SnippetResponse]:
        category_scores = self._predict_categories([snippet.text for snippet in snippets])
        pair_rows: list[dict[str, Any]] = []
        snippet_infos: list[dict[str, Any]] = []

        for snippet, scores in zip(snippets, category_scores):
            candidates = [
                (category, score)
                for category, score in scores.items()
                if score >= self.category_thresholds.get(category, 0.5)
            ]
            candidates.sort(key=lambda item: (-item[1], item[0]))
            max_score = max(scores.values()) if scores else 0.0
            response_score = candidates[0][1] if candidates else max_score
            info = {
                "snippet": snippet,
                "scores": scores,
                "candidates": candidates,
                "score": max(0.0, min(1.0, float(response_score))),
                "opinions": [],
                "raw_model_output": {"model_a_scores": scores, "model_b": []},
            }
            snippet_infos.append(info)
            for category, category_score in candidates:
                pair_rows.append(
                    {
                        "info": info,
                        "snippet": snippet,
                        "category": category,
                        "category_score": category_score,
                    }
                )

        if pair_rows:
            self._predict_opinions(pair_rows)

        output: list[SnippetResponse] = []
        for info in snippet_infos:
            snippet: SnippetCandidate = info["snippet"]
            opinions: list[OpinionResponse] = info["opinions"]
            categories = sorted({opinion.category for opinion in opinions})
            status = "success" if info["candidates"] else "skipped"
            output.append(
                SnippetResponse(
                    snippet_id=snippet.snippet_id,
                    text=snippet.text,
                    start=snippet.start,
                    end=snippet.end,
                    quality=snippet.quality,  # type: ignore[arg-type]
                    score=round(info["score"], 4),
                    category_hits=snippet.category_hits,  # type: ignore[arg-type]
                    model_status=status,  # type: ignore[arg-type]
                    categories=categories,  # type: ignore[arg-type]
                    opinions=opinions,
                    raw_model_output=info["raw_model_output"] if include_raw_model_output else None,
                )
            )
        return output

    def _predict_categories(self, texts: list[str]) -> list[dict[str, float]]:
        encoded = self.model_a_tokenizer(
            texts,
            truncation=True,
            max_length=self.model_a_max_length,
            padding=True,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with self.torch.inference_mode():
            logits = self.model_a(**encoded).logits
            probabilities = self.torch.sigmoid(logits).detach().cpu().tolist()
        return [
            {category: float(probability) for category, probability in zip(self.categories, row)}
            for row in probabilities
        ]

    def _predict_opinions(self, pair_rows: list[dict[str, Any]]) -> None:
        prefixes = [f"[CAT]={row['category']}" for row in pair_rows]
        texts = [row["snippet"].text for row in pair_rows]
        encoded = self.model_b_tokenizer(
            prefixes,
            texts,
            truncation="only_second",
            max_length=self.model_b_max_length,
            padding=True,
            return_offsets_mapping=True,
            return_tensors="pt",
        )
        offsets = encoded.pop("offset_mapping").tolist()
        sequence_ids = [encoded.sequence_ids(index) for index in range(len(pair_rows))]
        model_inputs = {key: value.to(self.device) for key, value in encoded.items()}

        with self.torch.inference_mode():
            outputs = self.model_b(**model_inputs)
            aspect_ids = outputs["aspect_logits"].argmax(dim=-1).detach().cpu().tolist()
            evidence_ids = outputs["evidence_logits"].argmax(dim=-1).detach().cpu().tolist()
            polarity_probs = self.torch.softmax(outputs["polarity_logits"], dim=-1).detach().cpu().tolist()

        for index, row in enumerate(pair_rows):
            category = row["category"]
            snippet: SnippetCandidate = row["snippet"]
            probs = [float(value) for value in polarity_probs[index]]
            non_none_indices = [0, 1, 2]
            best_idx = max(non_none_indices, key=lambda item: probs[item])
            none_idx = 3
            polarity = POLARITIES_WITH_NONE[best_idx]
            confidence = probs[best_idx]
            none_probability = probs[none_idx]
            margin = self.none_margins.get(category, 0.0)
            accepted = confidence - none_probability >= margin

            aspect_spans = decode_bio_spans(aspect_ids[index], offsets[index], sequence_ids[index])
            evidence_spans = decode_bio_spans(evidence_ids[index], offsets[index], sequence_ids[index])
            raw_item = {
                "category": category,
                "category_score": row["category_score"],
                "polarity_probs": {
                    label: probs[label_idx]
                    for label_idx, label in enumerate(POLARITIES_WITH_NONE)
                },
                "none_margin": margin,
                "accepted": accepted,
                "aspect_spans": aspect_spans,
                "evidence_spans": evidence_spans,
            }
            row["info"]["raw_model_output"]["model_b"].append(raw_item)

            if not accepted or not aspect_spans or not evidence_spans:
                continue

            aspect = self._span_response(snippet.text, aspect_spans[0])
            evidences = [self._span_response(snippet.text, span) for span in evidence_spans]
            evidences = [item for item in evidences if item is not None]
            if aspect is None or not evidences:
                continue

            row["info"]["opinions"].append(
                OpinionResponse(
                    category=category,  # type: ignore[arg-type]
                    aspect_term=aspect,
                    evidence_spans=evidences,
                    polarity=polarity,  # type: ignore[arg-type]
                    confidence=max(0.0, min(1.0, confidence)),
                )
            )

    @staticmethod
    def _span_response(snippet_text: str, span: tuple[int, int]) -> SpanResponse | None:
        start, end = int(span[0]), int(span[1])
        if start < 0 or end <= start or end > len(snippet_text):
            return None
        text = snippet_text[start:end]
        if not text.strip():
            return None
        return SpanResponse(text=text, start=start, end=end)
