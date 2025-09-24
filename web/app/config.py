from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    supabase_table: str = "volume_snapshots"
    supabase_latest_view: str = "volume_snapshots_latest"
    page_size_default: int = 100
    page_size_max: int = 200
    request_timeout: float = 15.0

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
            supabase_latest_view=os.getenv("SUPABASE_LATEST_VIEW", "volume_snapshots_latest"),
            page_size_default=int(os.getenv("PAGE_SIZE_DEFAULT", "100")),
            page_size_max=int(os.getenv("PAGE_SIZE_MAX", "200")),
            request_timeout=float(os.getenv("REQUEST_TIMEOUT", "15")),
        )
