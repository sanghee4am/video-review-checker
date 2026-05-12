"""Fetch a ParsedGuideline JSON directly from an external guideline tool.

Currently supports the `campaign-guideline-tool` (4ITM-solution) Vercel app,
which exposes a `/api/share/{id}/{opt}/parsed-guideline` endpoint returning
the same shape as `models.guideline.ParsedGuideline`.

Why this exists:
  guidelines authored in that tool never go through the `/api/guidelines/upload`
  or `/api/guidelines/parse-notion` flow, so `guidelines.gl_parsed_json` stays
  NULL and `review-by-path` fails with "가이드라인 없음". This module bridges the
  gap by reading `guidelines.gl_source_url` and, if it's a recognised
  campaign-guideline-tool share URL, fetching the structured JSON directly.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

from models.guideline import ParsedGuideline


# Matches share URLs like:
#   https://campaign-guideline-tool.vercel.app/share/<uuid>/<a|b|c|0|1|2>
#   https://guideline.4am.team/share/<uuid>/<a|b|c>          (future domain swap)
#   http://localhost:3001/share/<uuid>/<a>                   (local dev)
_SHARE_PATH_RE = re.compile(r"^/share/([^/]+)/([^/?#]+)/?$")

# Known hosts to accept. Any *.vercel.app deployment of the tool is fine, and
# we also accept the planned production swap to guideline.4am.team (kept here
# pre-emptively so a future swap does not require a code change).
_ALLOWED_HOST_SUFFIXES = (
    "campaign-guideline-tool.vercel.app",
    "guideline.4am.team",
    "localhost",
    "127.0.0.1",
)


def _is_allowed_host(host: str) -> bool:
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in _ALLOWED_HOST_SUFFIXES)


def parse_guideline_tool_share_url(url: str) -> Optional[Tuple[str, str, str]]:
    """If `url` is a campaign-guideline-tool share URL, return
    `(base_url, share_id, opt_slug)`. Returns None otherwise.

    `base_url` is `scheme://host[:port]` (no trailing slash) so callers can
    construct sibling URLs (e.g. the parsed-guideline API).
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if parsed.scheme not in ("http", "https"):
        return None
    if not _is_allowed_host(parsed.netloc.split(":")[0]):
        return None

    m = _SHARE_PATH_RE.match(parsed.path)
    if not m:
        return None

    share_id, opt = m.group(1), m.group(2)
    port = f":{parsed.port}" if parsed.port else ""
    base = f"{parsed.scheme}://{parsed.hostname}{port}"
    return base, share_id, opt


def fetch_parsed_guideline_from_share_url(
    url: str, *, timeout: float = 15.0
) -> Optional[ParsedGuideline]:
    """Fetch a ParsedGuideline from the tool's `/api/share/{id}/{opt}/parsed-guideline`
    sibling endpoint of the given share URL.

    Returns the validated ParsedGuideline, or None if the URL is not a
    recognised guideline-tool share URL. Raises on HTTP / validation errors so
    the caller can surface them.
    """
    parsed = parse_guideline_tool_share_url(url)
    if parsed is None:
        return None
    base, share_id, opt = parsed

    api_url = f"{base}/api/share/{share_id}/{opt}/parsed-guideline"
    resp = requests.get(api_url, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    return ParsedGuideline.model_validate(payload)
