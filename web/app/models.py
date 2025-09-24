from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class VolumeRow(BaseModel):
    id: int
    ticker: str
    last_trade_date: date
    previous_trade_date: date
    latest_volume: int = Field(..., ge=0)
    previous_volume: int = Field(..., ge=0)
    volume_ratio: Optional[float]
    volume_change_pct: Optional[float]
    is_spike: bool
    fetched_at_utc: datetime
    fetched_at_kst: datetime
    created_at: datetime


class PaginatedResponse(BaseModel):
    items: list[VolumeRow]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool
