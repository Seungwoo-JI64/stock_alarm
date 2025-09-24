from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    supabase_table: str = "volume_snapshots"
    tickers_file: str = "us_tickers.csv"
    chunk_size: int = 50
    yf_period: str = "5d"
    yf_interval: str = "1d"
    request_timeout: int = 30
    max_retries: int = 3

    @staticmethod
    def load() -> "Settings":
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not supabase_service_role_key:
            missing = []
            if not supabase_url:
                missing.append("SUPABASE_URL")
            if not supabase_service_role_key:
                missing.append("SUPABASE_SERVICE_ROLE_KEY")
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        return Settings(
            supabase_url=supabase_url.rstrip("/"),
            supabase_service_role_key=supabase_service_role_key,
            supabase_table=os.getenv("SUPABASE_TABLE", "volume_snapshots"),
            tickers_file=os.getenv("TICKERS_FILE", "us_tickers.csv"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "50")),
            yf_period=os.getenv("YF_PERIOD", "5d"),
            yf_interval=os.getenv("YF_INTERVAL", "1d"),
            request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
        )
