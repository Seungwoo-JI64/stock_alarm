from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

import pandas as pd
import yfinance as yf

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VolumeSnapshot:
    ticker: str
    last_trade_date: datetime
    previous_trade_date: datetime
    latest_volume: int
    previous_volume: int
    volume_ratio: Optional[float]
    volume_change_pct: Optional[float]
    is_spike: bool


def load_tickers(path: str | Path) -> List[str]:
    df = pd.read_csv(path, header=None, dtype=str)
    tickers = (
        df.iloc[:, 0].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
    )
    return [ticker.upper() for ticker in tickers]


def chunked(iterable: Iterable[str], size: int) -> Iterator[List[str]]:
    chunk: List[str] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _extract_volume_frame(raw: pd.DataFrame, ticker: str) -> Optional[pd.Series]:
    if raw.empty:
        return None

    try:
        if isinstance(raw.columns, pd.MultiIndex):
            volume_series = raw["Volume"][ticker]
        else:
            volume_series = raw["Volume"]
    except KeyError:
        return None

    volume_series = volume_series.dropna()
    if volume_series.empty:
        return None

    volume_series = pd.to_numeric(volume_series, errors="coerce").dropna().astype(int)
    idx = volume_series.index
    tzinfo = getattr(idx, "tz", None)
    if tzinfo is None:
        volume_series.index = idx.tz_localize(timezone.utc)
    else:
        volume_series.index = idx.tz_convert(timezone.utc)
    volume_series = volume_series.sort_index()

    if len(volume_series) < 2:
        return None

    return volume_series


def _build_snapshot(ticker: str, series: pd.Series) -> VolumeSnapshot:
    latest_volume = int(series.iloc[-1])
    previous_volume = int(series.iloc[-2])
    last_trade_date = series.index[-1].to_pydatetime()
    previous_trade_date = series.index[-2].to_pydatetime()

    if previous_volume <= 0:
        volume_ratio = None
        volume_change_pct = None
        is_spike = False
    else:
        volume_ratio = latest_volume / previous_volume
        volume_change_pct = (latest_volume - previous_volume) / previous_volume * 100
        is_spike = volume_ratio >= 2.0

    return VolumeSnapshot(
        ticker=ticker,
        last_trade_date=last_trade_date,
        previous_trade_date=previous_trade_date,
        latest_volume=latest_volume,
        previous_volume=previous_volume,
        volume_ratio=volume_ratio,
        volume_change_pct=volume_change_pct,
        is_spike=is_spike,
    )


def fetch_snapshots(settings: Settings, tickers_override: List[str] | None = None) -> List[VolumeSnapshot]:
    tickers = tickers_override or load_tickers(settings.tickers_file)
    logger.info("Loaded %d tickers", len(tickers))

    results: List[VolumeSnapshot] = []
    for chunk in chunked(tickers, settings.chunk_size):
        logger.debug("Downloading chunk of %d tickers", len(chunk))

        data = None
        for attempt in range(1, settings.max_retries + 1):
            try:
                data = yf.download(
                    tickers=chunk,
                    period=settings.yf_period,
                    interval=settings.yf_interval,
                    group_by="ticker",
                    auto_adjust=False,
                    threads=True,
                    progress=False,
                )
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Attempt %d/%d failed for chunk starting %s: %s",
                    attempt,
                    settings.max_retries,
                    chunk[0],
                    exc,
                )

        if data is None or data.empty:
            logger.warning("No data returned for chunk starting %s", chunk[0])
            continue
        for ticker in chunk:
            try:
                series = _extract_volume_frame(data, ticker)
            except Exception as exc:  # defensive against yfinance quirks
                logger.warning("Failed to parse data for %s: %s", ticker, exc)
                continue

            if series is None:
                logger.debug("Skipping %s due to insufficient data", ticker)
                continue

            snapshot = _build_snapshot(ticker, series)
            results.append(snapshot)

    logger.info("Generated %d snapshots", len(results))
    return results
