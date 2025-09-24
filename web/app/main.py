from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:  # optional for local development
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

from .config import Settings
from .models import PaginatedResponse, VolumeRow
from .supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

if load_dotenv is not None:  # Load .env before settings
    load_dotenv()

settings = Settings.load()
supabase_client = SupabaseClient(settings)

app = FastAPI(title="Stock Alarm", version="0.1.0")

assets_dir = Path(__file__).parent
templates = Jinja2Templates(directory=str(assets_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(assets_dir / "static")), name="static")


def get_settings() -> Settings:
    return settings


def get_client() -> SupabaseClient:
    return supabase_client


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await supabase_client.close()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, settings: Settings = Depends(get_settings)) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "page_size_default": settings.page_size_default,
        },
    )


@app.get("/api/volume-changes", response_model=PaginatedResponse)
async def volume_changes(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.page_size_default, ge=1, le=settings.page_size_max),
    client: SupabaseClient = Depends(get_client),
) -> PaginatedResponse:
    offset = (page - 1) * page_size

    try:
        rows, total = await client.fetch_latest(offset=offset, limit=page_size)
    except Exception as exc:  # pragma: no cover - supabase failure path
        logger.exception("Failed to fetch data from Supabase")
        raise HTTPException(status_code=502, detail="Failed to fetch data from Supabase") from exc

    items = [VolumeRow(**row) for row in rows]
    total = max(total, offset + len(items))
    has_next = offset + len(items) < total
    has_previous = page > 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
        has_previous=has_previous,
    )
