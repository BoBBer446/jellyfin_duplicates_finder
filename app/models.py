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


class DuplicateGroup(BaseModel):
    identifier: str
    keep_item_id: str
    items: list[DuplicateItem]
    delete_candidates: list[str]


class ScanSummary(BaseModel):
    total_items: int
    duplicate_groups: int
    duplicate_items_to_delete: int


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
    custom_sequences: list[str] | None = None

    @model_validator(mode="after")
    def validate_item_types(self) -> "JellyfinScanRequest":
        if not self.include_item_types:
            raise ValueError("include_item_types must not be empty")
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
