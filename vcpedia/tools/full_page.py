"""Full-page tool for VCPedia."""

from __future__ import annotations

from typing import Any

from ..wiki.api import VCPediaAPI
from ..wiki.cache import WikiTTLCache
from ..wiki.parser import limit_text
from .resolve import resolve_page


async def get_full_page(
    api: VCPediaAPI,
    cache: WikiTTLCache,
    query: str,
    max_chars: int = 16000,
) -> dict[str, Any]:
    """Return a rendered full page with infobox fields and section list."""
    resolved = await resolve_page(api, cache, query)
    if resolved.get("error"):
        return {
            "error": resolved.get("error"),
            "query": query,
            "candidates": resolved.get("candidates", []),
            "attempted_queries": resolved.get("attempted_queries", []),
        }

    bundle = resolved["bundle"]
    content = bundle.get("content", "")
    full_length = len(content)
    return {
        "query": query,
        "title": bundle.get("title", ""),
        "type": bundle.get("type", "page"),
        "url": bundle.get("url", ""),
        "summary": limit_text(bundle.get("summary", ""), 600),
        "fields": bundle.get("fields", {}),
        "sections": bundle.get("sections", []),
        "content": limit_text(content, max_chars),
        "content_chars": full_length,
        "is_truncated": full_length > max_chars,
        "ambiguous": resolved.get("ambiguous", False),
        "candidates": (
            resolved.get("candidates", [])[:2] if resolved.get("ambiguous") else []
        ),
    }
