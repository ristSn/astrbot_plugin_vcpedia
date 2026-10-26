"""Summary tool for VCPedia pages."""

from __future__ import annotations

from typing import Any

from ..wiki.api import VCPediaAPI
from ..wiki.cache import WikiTTLCache
from ..wiki.parser import limit_text
from .resolve import resolve_page


async def get_wiki_summary(
    api: VCPediaAPI,
    cache: WikiTTLCache,
    query: str,
    max_chars: int = 1200,
) -> dict[str, Any]:
    """Return the lead summary of the best matching page."""
    resolved = await resolve_page(api, cache, query)
    if resolved.get("error"):
        return {
            "error": resolved.get("error"),
            "query": query,
            "candidates": resolved.get("candidates", []),
            "attempted_queries": resolved.get("attempted_queries", []),
        }

    bundle = resolved["bundle"]
    page_type = bundle.get("type", "page")
    return {
        "query": query,
        "title": bundle.get("title", resolved.get("title", "")),
        "type": page_type,
        "url": bundle.get("url", ""),
        "summary": limit_text(bundle.get("summary", ""), max_chars),
        "sections": bundle.get("sections", [])[:12],
        "categories": bundle.get("categories", [])[:8],
        "ambiguous": resolved.get("ambiguous", False),
        "candidates": (
            resolved.get("candidates", [])[:3]
            if resolved.get("ambiguous") or page_type == "disambiguation"
            else []
        ),
    }
