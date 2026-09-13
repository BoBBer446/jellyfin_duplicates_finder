from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class DuplicateItem(BaseModel):
    id: str
    name: str
    path: str
    size: int = 0
    resolution: int = 0
    year: int | None = None
    width: int = 0
    height: int = 0
    codec: str = ""
    runtime_seconds: int = 0


class DuplicateGroup(BaseModel):
    identifier: str
    keep_item_id: str
    items: list[DuplicateItem]
    delete_candidates: list[str]
    match_reason: str = ""
    confidence: Literal["high", "medium"] = "medium"
    reclaimable_bytes: int = 0


class ScanSummary(BaseModel):
    total_items: int
    duplicate_groups: int
    duplicate_items_to_delete: int
    reclaimable_bytes: int = 0
    skipped_items: int = 0


class ScanResult(BaseModel):
    scan_id: str
    created_at: datetime
    source: Literal["jellyfin", "file"]
    summary: ScanSummary
    groups: list[DuplicateGroup]


class JellyfinScanRequest(BaseModel):
    base_url: HttpUrl
    api_key: str = Field(min_length=1)
    include_item_types: list[str] = Field(default_factory=lambda: ["Movie"])
    verify_ssl: bool = True
    custom_sequences: list[str] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_item_types(self) -> JellyfinScanRequest:
        if not self.include_item_types:
            raise ValueError("include_item_types must not be empty")
        if any(kind not in {"Movie", "Episode", "Series"} for kind in self.include_item_types):
            raise ValueError("Only Movie, Episode and Series are supported")
        self.include_item_types = list(
            dict.fromkeys(
                "Episode" if kind == "Series" else kind for kind in self.include_item_types
            )
        )
        if self.custom_sequences and any(
            not marker.strip() or len(marker) > 64 for marker in self.custom_sequences
        ):
            raise ValueError("Sequence markers must contain 1 to 64 characters")
        return self


class DeleteRequest(BaseModel):
    dry_run: bool = True
    item_ids: list[str] | None = None


class DeleteResult(BaseModel):
    scan_id: str
    dry_run: bool
    requested_ids: list[str]
    deleted_ids: list[str]
    failed_ids: dict[str, str]
