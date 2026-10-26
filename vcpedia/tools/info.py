"""Structured page information tool for VCPedia."""

from __future__ import annotations

from typing import Any

from ..wiki.api import VCPediaAPI
from ..wiki.cache import WikiTTLCache
from ..wiki.parser import find_section, limit_text
from .resolve import resolve_page


def _lyrics_excerpt(lyrics: str, max_chars: int = 800) -> str:
    lines = [line for line in (lyrics or "").splitlines() if line.strip()]
    return limit_text("\n".join(lines[:12]), max_chars)


async def get_page_info(
    api: VCPediaAPI,
    cache: WikiTTLCache,
    query: str,
    preferred_type: str | None = None,
    include_lyrics_excerpt: bool = False,
    max_chars: int = 3800,
) -> dict[str, Any]:
    """Return infobox fields, summary, staff and section metadata for a page."""
    resolved = await resolve_page(api, cache, query, preferred_type=preferred_type)
    if resolved.get("error"):
        return {
            "error": resolved.get("error"),
            "query": query,
            "candidates": resolved.get("candidates", []),
            "attempted_queries": resolved.get("attempted_queries", []),
        }

    bundle = resolved["bundle"]
    page_type = bundle.get("type", "page")
    versions = bundle.get("versions", [])
    payload: dict[str, Any] = {
        "query": query,
        "title": bundle.get("title", ""),
        "type": page_type,
        "url": bundle.get("url", ""),
        "summary": limit_text(bundle.get("summary", ""), min(700, max_chars // 3)),
        "fields": bundle.get("fields", {}),
        "sections": bundle.get("sections", [])[:20],
        "categories": bundle.get("categories", [])[:10],
        "links": bundle.get("links", [])[:8],
        "ambiguous": resolved.get("ambiguous", False),
        "candidates": (
            resolved.get("candidates", [])[:3]
            if resolved.get("ambiguous") or page_type == "disambiguation"
            else []
        ),
    }

    if len(versions) > 1:
        payload["versions"] = [version.get("fields", {}) for version in versions]
        payload["version_count"] = len(versions)

    if page_type == "song":
        payload["staff"] = bundle.get("staff", [])
        payload["achievements"] = bundle.get("achievements", [])
        payload["has_lyrics"] = bool(bundle.get("lyrics"))
        if include_lyrics_excerpt and bundle.get("lyrics"):
            payload["lyrics_excerpt"] = _lyrics_excerpt(bundle["lyrics"])

    if page_type == "album":
        all_tracks = bundle.get("tracks", [])
        payload["track_count"] = len(all_tracks)
        payload["tracks"] = all_tracks[:30]
        if len(all_tracks) > 30:
            payload["tracks_truncated"] = True
        if not all_tracks:
            tracklist_section = find_section(bundle.get("content", ""), "收录曲目")
            if not tracklist_section:
                tracklist_section = find_section(bundle.get("content", ""), "曲目")
            if tracklist_section:
                payload["tracklist"] = limit_text(
                    tracklist_section.get("content", ""), max_chars // 2
                )

    if preferred_type and page_type not in {preferred_type, "disambiguation"}:
        payload["note"] = f"匹配到的页面类型是 {page_type}，不是 {preferred_type}"

    return payload
