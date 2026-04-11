from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.models import DuplicateGroup, DuplicateItem, ScanSummary

_NUMBERED_SEQUENCE_PREFIXES = [
    "CD",
    "DVD",
    "DISC",
    "DISK",
    "VCD",
    "BD",
    "PART",
    "PT",
    "TEIL",
    "VOL",
    "VOLUME",
]
_ROMAN_PARTS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

DEFAULT_SEQUENCES = list(
    dict.fromkeys(
        [
            *(f"{prefix}{number}" for prefix in _NUMBERED_SEQUENCE_PREFIXES for number in range(1, 13)),
            *(f"{prefix}{number:02d}" for prefix in _NUMBERED_SEQUENCE_PREFIXES for number in range(1, 13)),
            *(f"PART{roman}" for roman in _ROMAN_PARTS),
            *(f"PT{roman}" for roman in _ROMAN_PARTS),
            *(f"TEIL{roman}" for roman in _ROMAN_PARTS),
            "DISC-A",
            "DISC-B",
            "DISK-A",
            "DISK-B",
            "SIDE-A",
            "SIDE-B",
        ]
    )
)


def _normalize_title(name: str, year: int | None) -> str:
    value = (name or "").strip()
    if year:
        value = re.sub(rf"\s*\({year}\)\s*$", "", value, flags=re.IGNORECASE)
    value = value.replace(".", " ").replace("_", " ").replace("-", " ")
    value = re.sub(r"[^a-zA-Z0-9 ]+", "", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _sequence_identifier(path: str, custom_sequences: list[str] | None) -> str | None:
    filename = Path(path).name
    sequence_list = custom_sequences or DEFAULT_SEQUENCES
    for sequence in sequence_list:
        pattern = _build_sequence_pattern(sequence)
        if re.search(pattern, filename, flags=re.IGNORECASE):
            return re.sub(r"[\s._-]+", "", sequence).upper()
    return None


def _build_sequence_pattern(sequence: str) -> str:
    normalized = re.sub(r"[\s._-]+", "", sequence).upper()
    num_match = re.match(r"^([A-Z]+)(\d+)$", normalized)
    if num_match:
        prefix, number_raw = num_match.groups()
        number = int(number_raw)
        return rf"(^|[^a-z0-9]){re.escape(prefix)}[\s._-]*0*{number}([^a-z0-9]|$)"

    roman_match = re.match(r"^([A-Z]+)([IVX]+)$", normalized)
    if roman_match:
        prefix, roman = roman_match.groups()
        return rf"(^|[^a-z0-9]){re.escape(prefix)}[\s._-]*{re.escape(roman)}([^a-z0-9]|$)"

    tokens = [token for token in re.split(r"[\s._-]+", sequence.strip()) if token]
    if not tokens:
        return r"$^"
    joined = r"[\s._-]*".join(re.escape(token) for token in tokens)
    return rf"(^|[^a-z0-9]){joined}([^a-z0-9]|$)"


def _item_from_raw(item: dict[str, Any]) -> DuplicateItem:
    media_sources = item.get("MediaSources") or []
    size = 0
    resolution = 0

    for source in media_sources:
        size += int(source.get("Size", 0) or 0)
        for stream in source.get("MediaStreams", []):
            if stream.get("Type") == "Video":
                width = int(stream.get("Width", 0) or 0)
                height = int(stream.get("Height", 0) or 0)
                resolution = max(resolution, width * height)

    return DuplicateItem(
        id=str(item.get("Id")),
        name=item.get("Name") or item.get("SortName") or "Unknown",
        path=item.get("Path") or "Unknown",
        size=size,
        resolution=resolution,
        year=item.get("ProductionYear"),
    )


def find_duplicate_groups(
    raw_items: list[dict[str, Any]],
    custom_sequences: list[str] | None = None,
) -> tuple[list[DuplicateGroup], ScanSummary]:
    grouped: dict[tuple[str, str, str], list[DuplicateItem]] = defaultdict(list)
    processed_count = 0

    for raw in raw_items:
        if raw.get("Id") is None:
            continue
        processed_count += 1
        normalized_name = _normalize_title(
            raw.get("SortName") or raw.get("Name") or "",
            raw.get("ProductionYear"),
        )
        year = str(raw.get("ProductionYear") or "unknown")
        path = raw.get("Path") or ""
        sequence = _sequence_identifier(path, custom_sequences) or ""
        key = (normalized_name, year, sequence)
        grouped[key].append(_item_from_raw(raw))

    duplicate_groups: list[DuplicateGroup] = []
    delete_total = 0

    for (title, year, sequence), items in grouped.items():
        if len(items) < 2:
            continue

        items_sorted = sorted(
            items,
            key=lambda entry: (entry.resolution, entry.size, entry.id),
            reverse=True,
        )
        keep_item = items_sorted[0]
        delete_candidates = [entry.id for entry in items_sorted[1:]]
        delete_total += len(delete_candidates)

        identifier = f"{title or 'unknown'} ({year})"
        if sequence:
            identifier = f"{identifier} [{sequence}]"

        duplicate_groups.append(
            DuplicateGroup(
                identifier=identifier,
                keep_item_id=keep_item.id,
                items=items_sorted,
                delete_candidates=delete_candidates,
            )
        )

    summary = ScanSummary(
        total_items=processed_count,
        duplicate_groups=len(duplicate_groups),
        duplicate_items_to_delete=delete_total,
    )
    return duplicate_groups, summary
