from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)
        base = settings.supabase_url.rstrip("/")
        self._base_url = f"{base}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Accept": "application/json",
            "Prefer": "count=exact",
        }

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_latest(self, *, offset: int, limit: int) -> Tuple[List[Dict[str, Any]], int]:
        view = self._settings.supabase_latest_view
        url = f"{self._base_url}/{view}"
        headers = dict(self._headers)
        headers["Range"] = f"items={offset}-{max(offset, offset + limit - 1)}"

        params = {
            "select": "id,ticker,last_trade_date,previous_trade_date,latest_volume,previous_volume,volume_ratio,volume_change_pct,is_spike,fetched_at_utc,fetched_at_kst,created_at",
            "order": "volume_change_pct.desc.nullslast",
        }

        response = await self._client.get(url, headers=headers, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Supabase request failed: %s", exc.response.text)
            raise

        total = _parse_total_count(response.headers.get("content-range"))
        data = response.json()
        return data, total


def _parse_total_count(header: str | None) -> int:
    if not header or "/" not in header:
        return 0
    try:
        total_part = header.split("/")[-1]
        return int(total_part) if total_part.isdigit() else 0
    except (ValueError, AttributeError):
        return 0
