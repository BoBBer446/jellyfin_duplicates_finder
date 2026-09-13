from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
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
            *(
                f"{prefix}{number}"
                for prefix in _NUMBERED_SEQUENCE_PREFIXES
                for number in range(1, 13)
            ),
            *(
                f"{prefix}{number:02d}"
                for prefix in _NUMBERED_SEQUENCE_PREFIXES
                for number in range(1, 13)
            ),
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
    import unicodedata

    text = unicodedata.normalize("NFKC", str(name or "")).casefold()
    if year:
        text = re.sub(rf"\s*\({re.escape(str(year))}\)\s*$", "", text)
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def _number(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


@lru_cache(maxsize=32)
def _sequence_patterns(custom_sequences: tuple[str, ...]):
    patterns = []
    for sequence in [*DEFAULT_SEQUENCES, *custom_sequences]:
        normalized = re.sub(r"[\s._-]+", "", sequence).upper()
        match = re.fullmatch(r"([A-Z]+)(\d+)", normalized)
        if match:
            prefix, number = match.groups()
            pattern = rf"{prefix}[\s._-]*0*{int(number)}"
            normalized = f"{prefix}{int(number)}"
        else:
            pattern = r"[\s._-]*".join(re.escape(t) for t in re.split(r"[\s._-]+", sequence) if t)
        if pattern:
            patterns.append((re.compile(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", re.I), normalized))
    return patterns


def _sequence_identifier(path: str, custom_sequences: list[str] | None) -> str:
    filename = path.replace(chr(92), "/").rsplit("/", 1)[-1]
    for pattern, normalized in _sequence_patterns(tuple(custom_sequences or [])):
        if pattern.search(filename):
            return normalized
    return ""


def _edition(raw: dict[str, Any]) -> str:
    if raw.get("EditionName"):
        return _normalize_title(raw["EditionName"], None)
    path = str(raw.get("Path") or "").replace("\\", "/").split("/")
    text = _normalize_title(" ".join(path[-2:]) + " " + str(raw.get("Name") or ""), None)
    markers = (
        "extended",
        "director s cut",
        "directors cut",
        "theatrical",
        "unrated",
        "uncut",
        "final cut",
        "special edition",
        "remastered",
    )
    return "|".join(marker for marker in markers if marker in text)


def _providers(raw: dict[str, Any]) -> dict[str, str]:
    values = raw.get("ProviderIds")
    if not isinstance(values, dict):
        return {}
    return {
        str(k).casefold(): str(v).strip().casefold()
        for k, v in values.items()
        if str(k).casefold() in {"tmdb", "imdb", "tvdb"} and v and str(v).strip()
    }


def _sources(raw):
    values = raw.get("MediaSources")
    return [s for s in values if isinstance(s, dict)] if isinstance(values, list) else []


def _paths(raw):
    return {
        str(p).replace("\\", "/").rstrip("/")
        for p in [raw.get("Path"), *(s.get("Path") for s in _sources(raw))]
        if p
    }


def _item_from_raw(raw: dict[str, Any]) -> DuplicateItem:
    sources = _sources(raw)
    video = [
        v
        for s in sources
        for v in (s.get("MediaStreams") if isinstance(s.get("MediaStreams"), list) else [])
        if isinstance(v, dict) and v.get("Type") == "Video"
    ]
    best = max(
        video,
        key=lambda v: _number(v.get("Width")) * _number(v.get("Height")),
        default={},
    )
    return DuplicateItem(
        id=str(raw["Id"]),
        name=str(raw.get("Name") or raw.get("SortName") or "Unbekannt"),
        path=str(raw.get("Path") or next(iter(sorted(_paths(raw))), "")),
        size=max((_number(s.get("Size")) for s in sources), default=0),
        resolution=_number(best.get("Width")) * _number(best.get("Height")),
        year=_number(raw.get("ProductionYear")) or None,
        width=_number(best.get("Width")),
        height=_number(best.get("Height")),
        codec=str(best.get("Codec") or ""),
        runtime_seconds=_number(raw.get("RunTimeTicks")) // 10_000_000,
    )


_EPISODE_IN_NAME = re.compile(
    r"(?<![a-z0-9])s(\d{1,3})[\s._-]*e(\d{1,4})"
    r"(?:(?:[\s._-]*e|[\s._]*-[\s._]*e?)(\d{1,4}))?(?![a-z0-9])",
    re.I,
)
_EPISODE_X_NAME = re.compile(r"(?<![a-z0-9])(\d{1,3})x(\d{1,4})(?:-(\d{1,4}))?(?![a-z0-9])", re.I)
_ABSOLUTE_IN_NAME = re.compile(
    r"(?<![a-z0-9])(ova|ona|folge|episode|ep)[\s._-]*(\d{1,4})(?![a-z0-9])", re.I
)


def _episode_filename_evidence(raw, season: int, episode: int, end: int):
    """Independent filename evidence; Jellyfin may assign the same number to different files."""
    paths = _paths(raw)
    if any(
        "plex versions" in [_normalize_title(part, None) for part in path.split("/")]
        for path in paths
    ):
        return None
    filenames = [path.rsplit("/", 1)[-1] for path in sorted(paths)]
    expected = (season, episode, end)
    path_evidence = False
    absolute = defaultdict(set)
    for index, text in enumerate([*filenames, str(raw.get("Name") or "")]):
        numbered = set()
        for pattern in (_EPISODE_IN_NAME, _EPISODE_X_NAME):
            for match in pattern.finditer(text):
                s, first, last = match.groups()
                numbered.add((int(s), int(first), int(last or first)))
        if numbered and numbered != {expected}:
            return None
        markers = list(_ABSOLUTE_IN_NAME.finditer(text))
        if index < len(filenames) and (numbered or markers):
            path_evidence = True
        for match in markers:
            kind, number = match.groups()
            family = kind.casefold() if kind.casefold() in {"ova", "ona"} else "absolute"
            absolute[family].add(int(number))
    if not path_evidence or any(len(numbers) != 1 for numbers in absolute.values()):
        return None
    return tuple(sorted((family, next(iter(numbers))) for family, numbers in absolute.items()))


def _keys(raw, sequences):
    kind = raw.get("Type") or "Movie"
    partition = (
        kind,
        _sequence_identifier(str(raw.get("Path") or ""), sequences),
        _edition(raw),
    )
    if kind == "Episode":
        series = raw.get("SeriesId")
        season, episode = raw.get("ParentIndexNumber"), raw.get("IndexNumber")
        end = raw.get("IndexNumberEnd") if raw.get("IndexNumberEnd") is not None else episode
        # Episode zero is frequently a catch-all for unrelated extras, not an identity.
        if (
            not series
            or type(season) is not int
            or season < 0
            or type(episode) is not int
            or episode <= 0
            or type(end) is not int
            or end < episode
        ):
            return []
        evidence = _episode_filename_evidence(raw, season, episode, end)
        title = _normalize_title(raw.get("Name") or "", None)
        if evidence is None or not title:
            return []
        return [(*partition, "episode", str(series), season, episode, end, evidence, title)]
    keys = [(*partition, "provider", k, v) for k, v in sorted(_providers(raw).items())]
    title = _normalize_title(
        raw.get("Name") or raw.get("SortName") or "", raw.get("ProductionYear")
    )
    year = _number(raw.get("ProductionYear"))
    if title and title not in {"movie", "film", "video", "unknown", "unbekannt"} and year:
        keys.append((*partition, "title", title, year))
    return keys


def _compatible(first, second):
    a, b = _providers(first), _providers(second)
    if any(a[k] != b[k] for k in a.keys() & b.keys()):
        return False
    x, y = _number(first.get("RunTimeTicks")), _number(second.get("RunTimeTicks"))
    return not (x and y and abs(x - y) > max(120 * 10_000_000, min(x, y) * 0.03))


def find_duplicate_groups(raw_items, custom_sequences=None):
    index = defaultdict(set)
    buckets = []
    bucket_keys = []
    seen_ids = set()
    skipped = 0
    eligible = []
    for raw in raw_items:
        if not isinstance(raw, dict) or not raw.get("Id") or str(raw["Id"]) in seen_ids:
            skipped += 1
            continue
        seen_ids.add(str(raw["Id"]))
        if (
            raw.get("IsFolder")
            or not isinstance(raw.get("Type", "Movie"), str)
            or raw.get("Type", "Movie") not in {"Movie", "Episode"}
            or (
                raw.get("MediaSources") is not None
                and not isinstance(raw.get("MediaSources"), list)
            )
            or len(_sources(raw)) > 1
            or not _paths(raw)
            or not _keys(raw, custom_sequences)
        ):
            skipped += 1
            continue
        eligible.append(raw)
    # Metadata-rich items first, so an unknown ID cannot bridge conflicting IDs.
    eligible.sort(key=lambda raw: (-len(_providers(raw)), str(raw["Id"])))
    for raw in eligible:
        keys = _keys(raw, custom_sequences)
        candidates = set().union(*(index[key] for key in keys))
        matches = [
            i
            for i in sorted(candidates)
            if bucket_keys[i].intersection(keys)
            and all(_compatible(raw, other) for other in buckets[i])
        ]
        if len(matches) == 1:
            i = matches[0]
        else:
            i = len(buckets)
            buckets.append([])
            bucket_keys.append(set(keys))
        buckets[i].append(raw)
        bucket_keys[i].intersection_update(keys)
        for key in keys:
            index[key].add(i)
    groups = []
    for bucket in buckets:
        if len(bucket) < 2:
            continue
        paths = [_paths(raw) for raw in bucket]
        if any(paths[i] & paths[j] for i in range(len(paths)) for j in range(i)):
            skipped += len(bucket)
            continue
        items = sorted(
            (_item_from_raw(raw) for raw in bucket),
            key=lambda item: (-item.resolution, -item.size, item.id),
        )
        common = set(_keys(bucket[0], custom_sequences))
        for raw in bucket[1:]:
            common.intersection_update(_keys(raw, custom_sequences))
        provider = any(key[3] == "provider" for key in common)
        episode = bucket[0].get("Type") == "Episode"
        reason = (
            "Gleiche externe Medien-ID"
            if provider
            else "Episodenmetadaten, Dateinummerierung und Titel stimmen überein"
            if episode
            else "Gleicher Titel und Erscheinungsjahr"
        )
        title, year = items[0].name, items[0].year
        groups.append(
            DuplicateGroup(
                identifier=f"{title} ({year})" if year else title,
                keep_item_id=items[0].id,
                items=items,
                delete_candidates=[item.id for item in items[1:]],
                match_reason=reason,
                confidence="high" if provider else "medium",
                reclaimable_bytes=sum(item.size for item in items[1:]),
            )
        )
    groups.sort(
        key=lambda group: (
            -group.reclaimable_bytes,
            group.identifier,
            group.keep_item_id,
        )
    )
    return groups, ScanSummary(
        total_items=len(raw_items),
        duplicate_groups=len(groups),
        duplicate_items_to_delete=sum(len(group.delete_candidates) for group in groups),
        reclaimable_bytes=sum(group.reclaimable_bytes for group in groups),
        skipped_items=skipped,
    )
