from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


CATEGORY_LEXICON: dict[str, list[str]] = {
    "price": ["주가", "목표가", "목표주가", "투자의견", "상향", "하향", "상승", "하락", "급등", "급락", "변동성"],
    "earnings": ["실적", "매출", "영업이익", "순이익", "적자", "흑자", "컨센서스", "가이던스", "어닝쇼크", "어닝서프라이즈"],
    "growth_outlook": ["성장", "전망", "기대", "예상", "수주", "수주잔고", "파이프라인", "점유율", "고객 확대", "증설", "생산능력", "CAPA", "회복", "확장"],
    "investment_financing": ["투자", "설비투자", "공장 신설", "유상증자", "무상증자", "제3자배정", "회사채", "CB", "BW", "자금조달", "인수", "합병", "M&A", "IPO", "스핀오프", "물적분할"],
    "management_governance": ["대표이사", "CEO", "경영진", "선임", "사임", "교체", "배당", "자사주", "소각", "주주환원", "횡령", "배임", "내부거래", "지배구조", "주주총회", "주주제안", "IR"],
    "regulation_macro": ["정책", "규제", "규제완화", "과징금", "제재", "금리", "환율", "경기", "경기둔화", "물가", "인플레이션", "경쟁", "가격경쟁", "신규 진입", "리스크"],
}

EVENT_KEYWORDS = ["결정", "발표", "추진", "검토", "선임", "사임", "교체", "부과", "시행", "확대", "축소", "체결", "완료", "개시", "중단", "인수"]
CHANGE_KEYWORDS = ["증가", "감소", "개선", "악화", "확대", "축소", "상승", "하락", "회복", "둔화", "상향", "하향"]
NUMERIC_SIGNAL_PATTERNS = [r"\d", r"%", r"억", r"조", r"원", r"배", r"bp", r"포인트", r"전년 대비", r"전분기 대비", r"yoy", r"qoq"]
DROP_PATTERNS = [r"무단전재", r"재배포 금지", r"기사 스크랩", r"클린뷰", r"프린트", r"댓글\s*\d*", r"구독하기"]


@dataclass(frozen=True)
class Sentence:
    sent_id: int
    text: str
    start: int
    end: int
    quality: str
    score: int
    category_hits: list[str]
    event_hits: list[str]
    change_hits: list[str]
    numeric_signal: bool
    incomplete: bool


@dataclass(frozen=True)
class SnippetCandidate:
    snippet_id: str
    text: str
    start: int
    end: int
    quality: str
    score: float
    category_hits: list[str]
    sent_ids: list[int]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def split_sentences_span_preserving(text: str) -> list[dict[str, Any]]:
    raw = str(text or "")
    if not raw.strip():
        return []

    pattern = re.compile(r".+?(?:[.!?](?:[\"'”’)\]]+)?(?=\s|$)|\n+|$)", re.S)
    spans: list[tuple[int, int]] = []
    for match in pattern.finditer(raw):
        start, end = match.span()
        chunk = raw[start:end]
        if not chunk.strip():
            continue
        left_trim = len(chunk) - len(chunk.lstrip())
        right_trim = len(chunk.rstrip())
        sent_start = start + left_trim
        sent_end = start + right_trim
        if sent_end > sent_start:
            spans.append((sent_start, sent_end))

    results: list[dict[str, Any]] = []
    for start, end in spans:
        text_value = raw[start:end].strip()
        if len(text_value) > 240 and "다 " in text_value and text_value.count(".") == 0:
            cursor = 0
            for piece in re.split(r"(?<=다)\s+", text_value):
                piece = piece.strip()
                if not piece:
                    continue
                local = text_value.find(piece, cursor)
                if local == -1:
                    local = cursor
                piece_start = start + local
                piece_end = piece_start + len(piece)
                results.append({"sent_id": len(results), "text": piece, "start": piece_start, "end": piece_end})
                cursor = local + len(piece)
            continue
        results.append({"sent_id": len(results), "text": text_value, "start": start, "end": end})
    return results


def is_incomplete_sentence(text: str) -> bool:
    value = normalize_space(text)
    if not value:
        return True
    if value.endswith((".", "!", "?")):
        return False
    if len(value) <= 20:
        return True
    return bool(re.search(r"(은|는|이|가|을|를|에|에서|보다|으로|로|및|또는|그리고|다만)$", value))


def classify_sentence_quality(text: str) -> dict[str, Any]:
    raw = str(text or "")
    lowered = raw.lower()
    if not raw.strip():
        return {"quality": "drop", "score": -1, "category_hits": [], "event_hits": [], "change_hits": [], "numeric_signal": False}
    if any(re.search(pattern, raw, flags=re.IGNORECASE) for pattern in DROP_PATTERNS):
        return {"quality": "drop", "score": -1, "category_hits": [], "event_hits": [], "change_hits": [], "numeric_signal": False}

    category_hits = [category for category, words in CATEGORY_LEXICON.items() if any(word.lower() in lowered for word in words)]
    event_hits = [word for word in EVENT_KEYWORDS if word in raw]
    change_hits = [word for word in CHANGE_KEYWORDS if word in raw]
    numeric_signal = any(re.search(pattern, lowered) for pattern in NUMERIC_SIGNAL_PATTERNS)
    score = len(category_hits) * 3 + len(event_hits) * 2 + len(change_hits) * 2 + int(numeric_signal)

    if category_hits or (numeric_signal and change_hits) or (event_hits and change_hits):
        quality = "strong"
    elif event_hits or change_hits or numeric_signal or is_incomplete_sentence(raw):
        quality = "weak"
    else:
        quality = "drop"
    return {
        "quality": quality,
        "score": score,
        "category_hits": category_hits,
        "event_hits": event_hits,
        "change_hits": change_hits,
        "numeric_signal": numeric_signal,
    }


def analyze_sentences(content: str) -> list[Sentence]:
    sentences: list[Sentence] = []
    for row in split_sentences_span_preserving(content):
        info = classify_sentence_quality(row["text"])
        sentences.append(
            Sentence(
                sent_id=int(row["sent_id"]),
                text=str(row["text"]),
                start=int(row["start"]),
                end=int(row["end"]),
                quality=str(info["quality"]),
                score=int(info["score"]),
                category_hits=list(info["category_hits"]),
                event_hits=list(info["event_hits"]),
                change_hits=list(info["change_hits"]),
                numeric_signal=bool(info["numeric_signal"]),
                incomplete=is_incomplete_sentence(str(row["text"])),
            )
        )
    return sentences


def _snippet_from_sentences(article_id: int, content: str, selected: list[Sentence], anchor_sent_id: int) -> SnippetCandidate | None:
    if not selected:
        return None
    start = min(item.start for item in selected)
    end = max(item.end for item in selected)
    text = content[start:end].strip()
    trim_left = len(content[start:end]) - len(content[start:end].lstrip())
    trim_right = len(content[start:end].rstrip())
    start += trim_left
    end = min(end, min(item.start for item in selected) + trim_right)
    if len(text) < 18:
        return None
    quality = "strong" if any(item.quality == "strong" for item in selected) else "weak"
    category_hits = sorted({category for item in selected for category in item.category_hits})
    raw_score = sum(max(0, item.score) for item in selected)
    score = round(min(raw_score / 25.0, 1.0), 4)
    return SnippetCandidate(
        snippet_id=f"{article_id}_snp_{anchor_sent_id + 1:04d}",
        text=text,
        start=start,
        end=end,
        quality=quality,
        score=score,
        category_hits=category_hits,
        sent_ids=[item.sent_id for item in selected],
    )


def build_snippet_candidates(article_id: int, content: str, include_weak: bool, max_snippets: int) -> list[SnippetCandidate]:
    sentences = analyze_sentences(content)
    candidates: list[SnippetCandidate] = []

    for idx, sentence in enumerate(sentences):
        if sentence.quality == "drop":
            continue
        if sentence.quality == "weak" and not include_weak:
            continue

        selected_indices = [idx]
        if sentence.incomplete and idx > 0 and sentences[idx - 1].quality != "drop":
            selected_indices.insert(0, idx - 1)
        if idx + 1 < len(sentences):
            next_sentence = sentences[idx + 1]
            same_flow = (
                next_sentence.quality != "drop"
                and (
                    sentence.numeric_signal and next_sentence.numeric_signal
                    or bool(set(sentence.category_hits) & set(next_sentence.category_hits))
                    or next_sentence.incomplete
                )
            )
            if same_flow:
                selected_indices.append(idx + 1)

        selected_indices = sorted(set(selected_indices))[:3]
        selected = [sentences[item] for item in selected_indices]
        candidate = _snippet_from_sentences(article_id, content, selected, sentence.sent_id)
        if candidate is not None:
            candidates.append(candidate)

    deduped: list[SnippetCandidate] = []
    seen: set[str] = set()
    ordered = sorted(
        candidates,
        key=lambda row: (
            0 if row.quality == "strong" else 1,
            -row.score,
            len(row.text),
            row.start,
        ),
    )
    for item in ordered:
        key = normalize_space(item.text.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_snippets:
            break
    return deduped


def candidates_debug_payload(candidates: list[SnippetCandidate]) -> str:
    return json.dumps([candidate.__dict__ for candidate in candidates], ensure_ascii=False)
