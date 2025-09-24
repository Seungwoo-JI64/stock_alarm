from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional
import time

import pandas as pd
import yfinance as yf

from .config import Settings

logger = logging.getLogger(__name__)


RATE_LIMIT_PATTERNS = (
    "Too Many Requests",
    "Rate limit",
    "YFRateLimitError",
)

RATE_LIMIT_BACKOFF_SECONDS = (300, 600, 1200)


class RateLimitExceeded(RuntimeError):
    """Raised when Yahoo Finance rate limiting is detected."""



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


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(pattern.lower() in message for pattern in RATE_LIMIT_PATTERNS)


def _has_sufficient_volume(df: Optional[pd.DataFrame]) -> bool:
    if df is None or df.empty:
        return False
    if "Volume" not in df.columns:
        return False
    volume = pd.to_numeric(df["Volume"], errors="coerce").dropna()
    if len(volume) < 2:
        return False
    if (volume <= 0).any():
        return False
    return True


def _fetch_history_for_ticker(ticker: str, settings: Settings) -> Optional[pd.DataFrame]:
    ticker_client = yf.Ticker(ticker)
    now_utc = datetime.now(timezone.utc)
    start_window = (now_utc - timedelta(days=7)).date()
    end_window = (now_utc + timedelta(days=1)).date()

    strategies = [
        ("period=1d", {"period": "1d"}),
        (
            "start-end",
            {
                "start": start_window,
                "end": end_window,
            },
        ),
        (f"period={settings.yf_period}", {"period": settings.yf_period}),
    ]

    last_history: Optional[pd.DataFrame] = None

    for label, kwargs in strategies:
        for attempt in range(1, settings.max_retries + 1):
            try:
                history = ticker_client.history(
                    interval=settings.yf_interval,
                    auto_adjust=False,
                    actions=False,
                    **kwargs,
                )
                last_history = history
            except Exception as exc:  # pragma: no cover - defensive
                if _is_rate_limit_error(exc):
                    raise RateLimitExceeded(str(exc)) from exc
                logger.warning(
                    "History request failed for %s (%s %d/%d): %s",
                    ticker,
                    label,
                    attempt,
                    settings.max_retries,
                    exc,
                )
                if attempt == settings.max_retries:
                    history = None
                else:
                    continue

            if _has_sufficient_volume(history):
                if label != "period=1d":
                    logger.debug("Fetched %s using %s", ticker, label)
                return history

            logger.debug(
                "Insufficient data for %s using %s; trying next strategy",
                ticker,
                label,
            )
            break

    return last_history


def _process_batch(batch: List[str], settings: Settings) -> List[VolumeSnapshot]:
    batch_results: List[VolumeSnapshot] = []
    for ticker in batch:
        try:
            history = _fetch_history_for_ticker(ticker, settings)
        except RateLimitExceeded:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to download history for %s: %s", ticker, exc)
            continue

        if history is None or history.empty:
            logger.debug("No history returned for %s", ticker)
            continue

        try:
            series = _extract_volume_frame(history, ticker)
        except Exception as exc:  # pragma: no cover - defensive
            if _is_rate_limit_error(exc):
                raise RateLimitExceeded(str(exc)) from exc
            logger.warning("Failed to parse volume data for %s: %s", ticker, exc)
            continue

        if series is None:
            logger.debug("Skipping %s due to insufficient data", ticker)
            continue

        snapshot = _build_snapshot(ticker, series)
        if snapshot is None:
            logger.debug("Skipping %s due to non-positive volumes", ticker)
            continue

        batch_results.append(snapshot)

    return batch_results


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


def _build_snapshot(ticker: str, series: pd.Series) -> Optional[VolumeSnapshot]:
    latest_volume = int(series.iloc[-1])
    previous_volume = int(series.iloc[-2])
    last_trade_date = series.index[-1].to_pydatetime()
    previous_trade_date = series.index[-2].to_pydatetime()

    if latest_volume <= 0 or previous_volume <= 0:
        return None

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

    if not tickers:
        return []

    results: List[VolumeSnapshot] = []
    total = len(tickers)
    batch_size = max(1, settings.chunk_size)
    pause_seconds = max(0, settings.batch_pause_seconds)
    batch_start = 0
    rate_limit_attempt = 0

    while batch_start < total:
        batch = tickers[batch_start : batch_start + batch_size]
        logger.info(
            "Processing tickers %d-%d",
            batch_start + 1,
            min(total, batch_start + len(batch)),
        )

        try:
            batch_results = _process_batch(batch, settings)
        except RateLimitExceeded as exc:
            if rate_limit_attempt >= len(RATE_LIMIT_BACKOFF_SECONDS):
                logger.error(
                    "Rate limit persisted after %d attempts; stopping early with %d snapshots collected. Last error: %s",
                    rate_limit_attempt,
                    len(results),
                    exc,
                )
                return results

            wait_seconds = RATE_LIMIT_BACKOFF_SECONDS[rate_limit_attempt]
            rate_limit_attempt += 1
            logger.warning(
                "Rate limit encountered (attempt %d/%d). Waiting %d seconds before retrying batch starting at index %d.",
                rate_limit_attempt,
                len(RATE_LIMIT_BACKOFF_SECONDS),
                wait_seconds,
                batch_start,
            )
            time.sleep(wait_seconds)
            continue

        rate_limit_attempt = 0
        results.extend(batch_results)
        batch_start += len(batch)

        if batch_start < total and pause_seconds:
            logger.debug(
                "Sleeping %d seconds before processing next batch", pause_seconds
            )
            time.sleep(pause_seconds)

    logger.info("Generated %d snapshots", len(results))
    return results
