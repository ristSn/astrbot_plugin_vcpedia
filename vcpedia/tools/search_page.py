"""Search helpers for VCPedia."""

from __future__ import annotations

from typing import Any

from ..wiki.api import VCPediaAPI
from ..wiki.cache import WikiTTLCache
from ..wiki.pages import get_page_bundles
from ..wiki.parser import strip_html


async def search_wiki_page(
    api: VCPediaAPI,
    query: str,
    limit: int = 5,
    cache: WikiTTLCache | None = None,
) -> dict[str, Any]:
    """Search VCPedia article pages.

    Args:
        api: VCPedia API client.
        query: Search keywords.
        limit: Maximum number of results.
        cache: Optional cache used to attach page types to results.

    Returns:
        A dict with ``results`` and ``totalhits``, or an ``error`` field.
    """
    keyword = (query or "").strip()
    if not keyword:
        return {"results": [], "error": "empty query"}

    data = await api.search(keyword, limit=limit)
    if data.get("error"):
        return {
            "results": [],
            "error": data.get("error"),
            "detail": data.get("detail", ""),
        }

    query_data = data.get("query") or {}
    raw_results = query_data.get("search") or []
    results = [
        {
            "title": row.get("title", ""),
            "snippet": strip_html(row.get("snippet", "")),
            "pageid": row.get("pageid"),
        }
        for row in raw_results[:limit]
        if row.get("title")
    ]

    if cache and results:
        bundles = await get_page_bundles(api, cache, [row["title"] for row in results])
        for row in results:
            bundle = bundles.get(row["title"]) or {}
            row["type"] = bundle.get("type", "")

    totalhits = (query_data.get("searchinfo") or {}).get("totalhits", len(results))
    return {
        "query": keyword,
        "results": results,
        "totalhits": totalhits,
    }
