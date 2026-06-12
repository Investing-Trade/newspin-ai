from __future__ import annotations

from collections.abc import Iterable


BIO_ID_TO_LABEL = {0: "O", 1: "B", 2: "I"}


def decode_bio_spans(
    label_ids: Iterable[int],
    offsets: Iterable[tuple[int, int] | list[int]],
    sequence_ids: Iterable[int | None],
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    active_start: int | None = None
    active_end: int | None = None

    for label_id, offset, seq_id in zip(label_ids, offsets, sequence_ids):
        if seq_id != 1:
            continue
        start, end = int(offset[0]), int(offset[1])
        if end <= start:
            continue

        label = BIO_ID_TO_LABEL.get(int(label_id), "O")
        if label == "B":
            if active_start is not None and active_end is not None:
                spans.append((active_start, active_end))
            active_start, active_end = start, end
        elif label == "I" and active_start is not None:
            active_end = end
        else:
            if active_start is not None and active_end is not None:
                spans.append((active_start, active_end))
            active_start, active_end = None, None

    if active_start is not None and active_end is not None:
        spans.append((active_start, active_end))
    return spans
