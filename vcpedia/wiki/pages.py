"""Fetch, parse, and cache VCPedia page bundles."""

from __future__ import annotations

from typing import Any

from .api import VCPediaAPI
from .cache import WikiTTLCache
from .parser import (
    extract_achievements,
    extract_infobox,
    extract_lyrics,
    extract_staff,
    extract_tracks,
    intro_text,
    normalize_title_for_match,
    render_wikitext,
    section_titles,
    split_sections,
)


def cache_key(title: str) -> str:
    """Build a stable cache key for a page title."""
    return f"page:{normalize_title_for_match(title)}"


def _clean_summary(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _choose_summary(extract: str, rendered: str) -> str:
    """Pick a useful summary, falling back when TextExtracts is too short."""
    summary = _clean_summary(extract)
    if len(summary) < 30:
        intro = _clean_summary(intro_text(rendered))
        if len(intro) > len(summary):
            summary = intro
    if len(summary) < 30:
        for section in split_sections(rendered):
            if section.get("title") and section.get("content"):
                candidate = _clean_summary(section["content"])
                if len(candidate) > len(summary):
                    summary = candidate
                break
    return summary


def build_bundle(page: dict[str, Any], fallback_url: str = "") -> dict[str, Any]:
    """Turn a raw API page into a parsed bundle shared by all tools."""
    title = page.get("title", "")
    if page.get("missing"):
        return {
            "title": title,
            "pageid": page.get("pageid"),
            "url": page.get("fullurl") or fallback_url,
            "missing": True,
            "error": "page not found",
            "type": "missing",
            "summary": "",
            "fields": {},
            "versions": [],
            "staff": [],
            "achievements": [],
            "tracks": [],
            "links": [],
            "categories": [],
            "sections": [],
            "content": "",
            "lyrics": "",
        }

    wikitext = page.get("wikitext", "") or ""
    infobox = extract_infobox(wikitext)
    rendered = render_wikitext(wikitext)
    summary = _choose_summary(page.get("extract", ""), rendered)

    return {
        "title": title,
        "pageid": page.get("pageid"),
        "url": page.get("fullurl") or fallback_url,
        "missing": False,
        "error": "",
        "type": infobox.get("type", "page"),
        "template": infobox.get("template", ""),
        "summary": summary,
        "fields": infobox.get("fields", {}),
        "versions": infobox.get("versions", []),
        "staff": extract_staff(wikitext),
        "achievements": extract_achievements(wikitext),
        "tracks": extract_tracks(wikitext),
        "links": infobox.get("links", []),
        "categories": page.get("categories", []),
        "sections": section_titles(rendered),
        "content": rendered,
        "lyrics": extract_lyrics(rendered),
        "length": page.get("length", 0),
        "touched": page.get("touched", ""),
    }


def _missing_bundle(title: str, error: str = "page not found") -> dict[str, Any]:
    return {
        "title": title,
        "url": "",
        "missing": True,
        "error": error,
        "type": "missing",
        "summary": "",
        "fields": {},
        "versions": [],
        "staff": [],
        "achievements": [],
        "tracks": [],
        "links": [],
        "categories": [],
        "sections": [],
        "content": "",
        "lyrics": "",
    }


async def get_page_bundles(
    api: VCPediaAPI,
    cache: WikiTTLCache,
    titles: list[str],
    with_extracts: bool = True,
) -> dict[str, dict[str, Any]]:
    """Fetch several pages in one API call, using the cache when possible.

    Args:
        api: VCPedia API client.
        cache: Shared page cache.
        titles: Page titles to fetch. Duplicates are ignored.
        with_extracts: Whether to request intro extracts from TextExtracts.

    Returns:
        A mapping from every requested title to its parsed bundle.
    """
    requested: list[str] = []
    for title in titles:
        title = (title or "").strip()
        if title and title not in requested:
            requested.append(title)
    if not requested:
        return {}

    result: dict[str, dict[str, Any]] = {}
    pending: list[str] = []
    for title in requested:
        cached = cache.get(cache_key(title))
        if cached:
            result[title] = cached
        else:
            pending.append(title)

    if not pending:
        return result

    data = await api.get_pages(pending, with_extracts=with_extracts)
    if data.get("error"):
        for title in pending:
            result[title] = _missing_bundle(title, str(data.get("error")))
        return result

    pages = data.get("pages", [])
    pages_by_title: dict[str, dict[str, Any]] = {}
    for page in pages:
        page_title = page.get("title", "")
        if page_title:
            pages_by_title[normalize_title_for_match(page_title)] = page

    redirect_map: dict[str, str] = {}
    for redirect in data.get("redirects", []) or []:
        if isinstance(redirect, dict) and redirect.get("from") and redirect.get("to"):
            redirect_map[normalize_title_for_match(redirect["from"])] = redirect["to"]

    for title in pending:
        normalized = normalize_title_for_match(title)
        page = pages_by_title.get(normalized)
        if page is None and normalized in redirect_map:
            target = redirect_map[normalized]
            page = pages_by_title.get(normalize_title_for_match(target))

        if page is None:
            result[title] = _missing_bundle(title)
            continue

        bundle = build_bundle(page, fallback_url=api.page_url(page.get("title", title)))
        result[title] = bundle
        cache.set(cache_key(title), bundle)
        if page.get("title"):
            cache.set(cache_key(page["title"]), bundle)

    return result


async def get_page_bundle(
    api: VCPediaAPI,
    cache: WikiTTLCache,
    title: str,
) -> dict[str, Any]:
    """Fetch a single parsed page bundle."""
    bundles = await get_page_bundles(api, cache, [title])
    return bundles.get(title) or _missing_bundle(title)
