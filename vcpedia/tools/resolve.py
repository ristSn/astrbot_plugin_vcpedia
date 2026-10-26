"""Resolve free-form questions to VCPedia page titles."""

from __future__ import annotations

import re
from typing import Any

from ..wiki.api import VCPediaAPI
from ..wiki.cache import WikiTTLCache
from ..wiki.pages import get_page_bundles
from ..wiki.parser import normalize_title_for_match, title_variants
from .search_page import search_wiki_page

DIRECT_TITLE_RE = re.compile(
    r"^(?:title|页面|page|条目|词条)\s*[:：]\s*(.+)$", re.IGNORECASE
)
PREFIX_RE = re.compile(
    r"^(?:请问|麻烦|帮我|帮忙|我想|想知道|想了解|了解一下|介绍一下|查一下|查查|查|搜一下|搜索|查找|看看|问一下|问下|关于|有关)\s*",
    re.IGNORECASE,
)

QUERY_SUFFIXES = (
    "这首歌的歌词",
    "那首歌的歌词",
    "的收录曲目",
    "的收录歌曲",
    "收录了哪些歌曲",
    "收录哪些歌曲",
    "收录了哪些歌",
    "收录哪些歌",
    "收录的歌曲",
    "收录的曲目",
    "收录曲目",
    "收录歌曲",
    "有哪些歌曲",
    "有哪些歌",
    "的歌曲",
    "歌曲列表",
    "曲目列表",
    "这首歌",
    "那首歌",
    "的歌词",
    "歌词",
    "是什么歌",
    "是哪首歌",
    "是什么",
    "是谁",
    "怎么样",
    "的资料",
    "的信息",
    "的介绍",
    "的页面",
    "页面",
    "条目",
)

TYPE_HINTS = {
    "song": " 歌曲",
    "producer": " P主",
    "voicebank": " 虚拟歌手",
    "album": " 专辑",
}

QUERY_PUNCTUATION = " \t\r\n\"'“”‘’《》「」『』。！？?!"


def normalize_query_text(text: str) -> str:
    """Strip polite prefixes, quotes, and question suffixes from a query."""
    query = (text or "").strip()
    if not query:
        return ""

    query = query.strip(QUERY_PUNCTUATION)
    query = PREFIX_RE.sub("", query).strip()

    changed = True
    while changed:
        changed = False
        for suffix in QUERY_SUFFIXES:
            if query.endswith(suffix) and len(query) > len(suffix):
                query = query[: -len(suffix)].strip()
                changed = True
                break

    return query.strip(QUERY_PUNCTUATION)


def build_search_queries(query: str, preferred_type: str | None = None) -> list[str]:
    """Build a small set of search queries, including entity-type hints."""
    queries: list[str] = []

    def add(value: str) -> None:
        value = (value or "").strip()
        if value and value not in queries:
            queries.append(value)

    add(query)
    for variant in title_variants(query):
        add(variant)

    if preferred_type and preferred_type in TYPE_HINTS:
        add(f"{query}{TYPE_HINTS[preferred_type]}")

    return queries[:4]


def _score_result(
    row: dict[str, Any],
    query: str,
    preferred_type: str | None,
    bundle: dict[str, Any] | None,
) -> int:
    title = row.get("title", "")
    snippet = row.get("snippet", "")
    title_norm = normalize_title_for_match(title)
    query_norm = normalize_title_for_match(query)
    snippet_norm = normalize_title_for_match(snippet)
    score = 0

    if title_norm == query_norm:
        score += 40
    elif title_norm.startswith(f"{query_norm}("):
        score += 18
    elif query_norm and query_norm in title_norm:
        score += 8

    if query_norm and query_norm in snippet_norm:
        score += 4

    tokens = [
        normalize_title_for_match(token) for token in re.split(r"[\s,，、]+", query)
    ]
    tokens = [token for token in tokens if token]
    if tokens:
        matched = sum(
            1 for token in tokens if token in title_norm or token in snippet_norm
        )
        score += matched * 5
        score -= (len(tokens) - matched) * 4

    if bundle:
        page_type = bundle.get("type", "page")
        if bundle.get("missing"):
            score -= 30
        elif page_type == "disambiguation":
            score += 2 if preferred_type in (None, "summary") else -12
        elif preferred_type and page_type == preferred_type:
            score += 20
        elif preferred_type and page_type not in {"page", preferred_type}:
            score -= 8

    return score


def _candidate(
    title: str, row: dict[str, Any], bundle: dict[str, Any] | None, score: int
) -> dict[str, Any]:
    return {
        "title": title,
        "snippet": row.get("snippet", ""),
        "source_query": row.get("source_query", ""),
        "type": (bundle or {}).get("type", ""),
        "url": (bundle or {}).get("url", ""),
        "score": score,
        "missing": bool((bundle or {}).get("missing")),
    }


async def resolve_page(
    api: VCPediaAPI,
    cache: WikiTTLCache,
    query: str,
    preferred_type: str | None = None,
    max_candidates: int = 5,
) -> dict[str, Any]:
    """Resolve a question or keyword to the most likely page bundle.

    Args:
        api: VCPedia API client.
        cache: Shared page cache.
        query: User question or page keyword.
        preferred_type: Optional song/producer/voicebank/album preference.
        max_candidates: Maximum candidates returned for ambiguity handling.

    Returns:
        A dict containing ``bundle``, ``candidates``, and attempt metadata, or
        an ``error`` field when nothing was found.
    """
    raw_query = (query or "").strip()
    if not raw_query:
        return {"error": "empty query", "query": raw_query, "candidates": []}

    direct = DIRECT_TITLE_RE.match(raw_query)
    if direct:
        title = direct.group(1).strip()
        bundles = await get_page_bundles(api, cache, title_variants(title))
        for variant in title_variants(title):
            bundle = bundles.get(variant)
            if bundle and not bundle.get("missing"):
                return {
                    "query": raw_query,
                    "title": bundle.get("title", variant),
                    "bundle": bundle,
                    "candidates": [
                        {
                            "title": bundle.get("title", variant),
                            "snippet": bundle.get("summary", "")[:160],
                            "type": bundle.get("type", ""),
                            "url": bundle.get("url", ""),
                            "score": 100,
                            "missing": False,
                        }
                    ],
                    "attempted_queries": [title],
                    "ambiguous": False,
                }
        return {
            "error": "page not found",
            "query": raw_query,
            "title": title,
            "candidates": [],
            "attempted_queries": [title],
        }

    normalized = normalize_query_text(raw_query) or raw_query
    search_queries = build_search_queries(normalized, preferred_type)

    pool: dict[str, dict[str, Any]] = {}
    attempted_queries: list[str] = []
    for search_query in search_queries:
        result = await search_wiki_page(api, search_query, limit=5)
        attempted_queries.append(search_query)
        for row in result.get("results", []):
            title = row.get("title", "")
            if not title or title in pool:
                continue
            pool[title] = {
                "title": title,
                "snippet": row.get("snippet", ""),
                "source_query": search_query,
            }

    if not pool:
        return {
            "error": "page not found",
            "query": raw_query,
            "candidates": [],
            "attempted_queries": attempted_queries,
        }

    check_titles: list[str] = []
    normalized_query = normalize_title_for_match(normalized)
    for title in pool:
        if (
            normalize_title_for_match(title) == normalized_query
            and title not in check_titles
        ):
            check_titles.append(title)
    for title in pool:
        if len(check_titles) >= 6:
            break
        if title not in check_titles:
            check_titles.append(title)

    bundles = await get_page_bundles(api, cache, check_titles)

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for order, (title, row) in enumerate(pool.items()):
        bundle = bundles.get(title)
        score = _score_result(row, normalized, preferred_type, bundle)
        scored.append((score, order, _candidate(title, row, bundle, score)))

    scored.sort(key=lambda item: (-item[0], item[1]))
    candidates = [item[2] for item in scored[:max_candidates]]
    best_title = candidates[0]["title"]
    best_bundle = bundles.get(best_title)
    if not best_bundle or best_bundle.get("missing"):
        extra = await get_page_bundles(api, cache, [best_title])
        best_bundle = extra.get(best_title)

    if not best_bundle or best_bundle.get("missing"):
        return {
            "error": "page not found",
            "query": raw_query,
            "candidates": candidates,
            "attempted_queries": attempted_queries,
        }

    ambiguous = (
        len(candidates) > 1
        and candidates[0].get("type") == candidates[1].get("type")
        and candidates[0]["score"] - candidates[1]["score"] < 6
    )

    return {
        "query": raw_query,
        "title": best_bundle.get("title", best_title),
        "bundle": best_bundle,
        "candidates": candidates,
        "attempted_queries": attempted_queries,
        "ambiguous": ambiguous,
    }
