from __future__ import annotations

import os
from typing import Any, Dict, Tuple

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_LATEST_VIEW = os.getenv("SUPABASE_LATEST_VIEW", "volume_snapshots_latest")
PAGE_SIZE_DEFAULT = int(os.getenv("PAGE_SIZE_DEFAULT", "100"))
PAGE_SIZE_MAX = int(os.getenv("PAGE_SIZE_MAX", "200"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15"))

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables are required.")

REST_BASE = SUPABASE_URL.rstrip("/") + "/rest/v1/"
SELECT_COLUMNS = (
    "id,ticker,last_trade_date,previous_trade_date,latest_volume,previous_volume,"
    "volume_ratio,volume_change_pct,is_spike,fetched_at_utc,fetched_at_kst,created_at"
)

app = Flask(__name__)


def _parse_content_range(header: str | None) -> int:
    if not header or "/" not in header:
        return 0
    try:
        _, total = header.split("/")
        return int(total)
    except (ValueError, TypeError):
        return 0


def _clamp_page_size(page_size: int) -> int:
    return max(1, min(page_size, PAGE_SIZE_MAX))


def fetch_latest_snapshots(page: int, page_size: int) -> Tuple[list[Dict[str, Any]], Dict[str, Any]]:
    safe_page = max(1, page)
    safe_page_size = _clamp_page_size(page_size)
    offset = (safe_page - 1) * safe_page_size
    end = offset + safe_page_size - 1

    url = REST_BASE + SUPABASE_LATEST_VIEW
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Range": f"items={offset}-{end}",
    }
    params = {
        "select": SELECT_COLUMNS,
        "order": "volume_change_pct.desc.nullslast",
    }

    response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    total = _parse_content_range(response.headers.get("content-range"))
    items = response.json()

    has_next = offset + len(items) < total
    has_previous = safe_page > 1

    meta = {
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "has_next": has_next,
        "has_previous": has_previous,
    }
    return items, meta


@app.route("/")
def index() -> str:
    page = request.args.get("page", default=1, type=int)
    page_size = request.args.get("page_size", default=PAGE_SIZE_DEFAULT, type=int)

    try:
        items, meta = fetch_latest_snapshots(page, page_size)
    except requests.HTTPError as exc:
        app.logger.error("Supabase HTTP error: %s", exc.response.text if exc.response else exc)
        return render_template(
            "error.html",
            message="Supabase에서 데이터를 불러오는 중 오류가 발생했습니다.",
            status_code=exc.response.status_code if exc.response else 500,
        ), 502
    except requests.RequestException:
        app.logger.exception("Supabase 요청 실패")
        return render_template(
            "error.html",
            message="Supabase와 통신할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            status_code=502,
        ), 502

    return render_template(
        "index.html",
        items=items,
        meta=meta,
        page_title="US Volume Spike Monitor",
    )


@app.route("/api/volume-changes")
def api_volume_changes():
    page = request.args.get("page", default=1, type=int)
    page_size = request.args.get("page_size", default=PAGE_SIZE_DEFAULT, type=int)

    try:
        items, meta = fetch_latest_snapshots(page, page_size)
    except requests.HTTPError as exc:
        return (
            jsonify(
                {
                    "error": "supabase_http_error",
                    "status": exc.response.status_code if exc.response else 500,
                    "details": exc.response.text if exc.response else str(exc),
                }
            ),
            502,
        )
    except requests.RequestException as exc:
        return (
            jsonify(
                {
                    "error": "supabase_request_failed",
                    "message": str(exc),
                }
            ),
            502,
        )

    return jsonify({"items": items, "meta": meta})


@app.route("/healthz")
def healthcheck() -> tuple[str, int]:
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
