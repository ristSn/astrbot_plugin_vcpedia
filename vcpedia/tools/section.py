"""Section tool for VCPedia pages."""

from __future__ import annotations

from typing import Any

from ..wiki.api import VCPediaAPI
from ..wiki.cache import WikiTTLCache
from ..wiki.parser import find_section, limit_text
from .resolve import resolve_page


async def get_page_section(
    api: VCPediaAPI,
    cache: WikiTTLCache,
    query: str,
    section: str,
    max_chars: int = 3000,
) -> dict[str, Any]:
    """Return one named section from the best matching page."""
    resolved = await resolve_page(api, cache, query)
    if resolved.get("error"):
        return {
            "error": resolved.get("error"),
            "query": query,
            "section": section,
            "candidates": resolved.get("candidates", []),
            "attempted_queries": resolved.get("attempted_queries", []),
        }

    bundle = resolved["bundle"]
    found = find_section(bundle.get("content", ""), section)
    if not found:
        return {
            "query": query,
            "title": bundle.get("title", ""),
            "type": bundle.get("type", "page"),
            "url": bundle.get("url", ""),
            "error": "section not found",
            "section": section,
            "available_sections": bundle.get("sections", []),
        }

    return {
        "query": query,
        "title": bundle.get("title", ""),
        "type": bundle.get("type", "page"),
        "url": bundle.get("url", ""),
        "section": found.get("title", section),
        "available_sections": bundle.get("sections", []),
        "content": limit_text(found.get("content", ""), max_chars),
        "ambiguous": resolved.get("ambiguous", False),
        "candidates": (
            resolved.get("candidates", [])[:2] if resolved.get("ambiguous") else []
        ),
    }
