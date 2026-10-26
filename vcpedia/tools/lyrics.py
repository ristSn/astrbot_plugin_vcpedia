"""Lyrics tool for VCPedia song pages."""

from __future__ import annotations

from typing import Any

from ..wiki.api import VCPediaAPI
from ..wiki.cache import WikiTTLCache
from ..wiki.parser import limit_text
from .resolve import resolve_page


async def get_lyrics(
    api: VCPediaAPI,
    cache: WikiTTLCache,
    query: str,
    max_chars: int = 6000,
) -> dict[str, Any]:
    """Return the full lyrics section of the best matching song page."""
    resolved = await resolve_page(api, cache, query, preferred_type="song")
    if resolved.get("error"):
        return {
            "error": resolved.get("error"),
            "query": query,
            "candidates": resolved.get("candidates", []),
            "attempted_queries": resolved.get("attempted_queries", []),
        }

    bundle = resolved["bundle"]
    lyrics = bundle.get("lyrics", "")
    if not lyrics:
        return {
            "query": query,
            "title": bundle.get("title", ""),
            "type": bundle.get("type", "page"),
            "url": bundle.get("url", ""),
            "error": "lyrics not found",
            "sections": bundle.get("sections", []),
            "candidates": resolved.get("candidates", [])[:3],
        }

    full_length = len(lyrics)
    non_empty_lines = len([line for line in lyrics.splitlines() if line.strip()])
    return {
        "query": query,
        "title": bundle.get("title", ""),
        "type": bundle.get("type", "page"),
        "url": bundle.get("url", ""),
        "section": "歌词",
        "line_count": non_empty_lines,
        "lyrics": limit_text(lyrics, max_chars),
        "is_truncated": full_length > max_chars,
        "ambiguous": resolved.get("ambiguous", False),
        "candidates": (
            resolved.get("candidates", [])[:2] if resolved.get("ambiguous") else []
        ),
    }
