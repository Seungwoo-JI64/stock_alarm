from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List
from uuid import UUID

import requests

from .config import Settings
from .volume_fetcher import VolumeSnapshot, chunked

logger = logging.getLogger(__name__)


class SupabaseUploader:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()
        self._base_url = f"{settings.supabase_url}/rest/v1/{settings.supabase_table}"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def upload(self, *, batch_id: UUID, snapshots: List[VolumeSnapshot], fetched_at_utc: datetime, fetched_at_kst: datetime) -> None:
        if not snapshots:
            logger.warning("No snapshots to upload.")
            return

        total = len(snapshots)
        for idx, chunk in enumerate(chunked(snapshots, 500), start=1):
            payload = [
                self._prepare_payload(
                    snapshot=snapshot,
                    batch_id=batch_id,
                    fetched_at_utc=fetched_at_utc,
                    fetched_at_kst=fetched_at_kst,
                )
                for snapshot in chunk
            ]
            self._post_payload(payload)
            logger.info("Uploaded chunk %d/%d", idx, (total + 499) // 500)

    def _prepare_payload(
        self,
        *,
        snapshot: VolumeSnapshot,
        batch_id: UUID,
        fetched_at_utc: datetime,
        fetched_at_kst: datetime,
    ) -> dict:
        return {
            "batch_id": str(batch_id),
            "ticker": snapshot.ticker,
            "last_trade_date": snapshot.last_trade_date.date().isoformat(),
            "previous_trade_date": snapshot.previous_trade_date.date().isoformat(),
            "latest_volume": snapshot.latest_volume,
            "previous_volume": snapshot.previous_volume,
            "volume_ratio": snapshot.volume_ratio,
            "volume_change_pct": snapshot.volume_change_pct,
            "is_spike": snapshot.is_spike,
            "fetched_at_utc": fetched_at_utc.isoformat(),
            "fetched_at_kst": fetched_at_kst.isoformat(),
        }

    def _post_payload(self, payload: List[dict]) -> None:
        params = {"on_conflict": "batch_id,ticker"}
        response = self._session.post(
            self._base_url,
            headers=self._headers,
            params=params,
            data=json.dumps(payload),
            timeout=self._settings.request_timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("Supabase upload failed: %s", response.text)
            raise exc


def upload_snapshots(
    *,
    settings: Settings,
    batch_id: UUID,
    snapshots: List[VolumeSnapshot],
    fetched_at_utc: datetime,
    fetched_at_kst: datetime,
) -> None:
    uploader = SupabaseUploader(settings)
    uploader.upload(
        batch_id=batch_id,
        snapshots=snapshots,
        fetched_at_utc=fetched_at_utc,
        fetched_at_kst=fetched_at_kst,
    )
