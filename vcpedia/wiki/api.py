"""Minimal async client for the VCPedia MediaWiki API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

import httpx


def _derive_site_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    if not parts.scheme or not parts.netloc:
        return "https://vcpedia.cn"
    return f"{parts.scheme}://{parts.netloc}"


def _extract_content(page: dict[str, Any]) -> str:
    revisions = page.get("revisions") or []
    if not revisions:
        return ""

    revision = revisions[0] or {}
    slots = revision.get("slots") or {}
    main_slot = slots.get("main") or {}
    content = main_slot.get("content")
    if content is None:
        content = revision.get("*")
    if isinstance(content, dict):
        content = content.get("*", "")
    return content or ""


def _normalize_pages(raw_pages: Any) -> list[dict[str, Any]]:
    if isinstance(raw_pages, dict):
        return [page for page in raw_pages.values() if isinstance(page, dict)]
    if isinstance(raw_pages, list):
        return [page for page in raw_pages if isinstance(page, dict)]
    return []


class VCPediaAPI:
    """Thin wrapper around the MediaWiki action API used by VCPedia."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 12.0,
        user_agent: str = "astrbot-plugin-vcpedia/1.0",
    ):
        self.base_url = base_url
        self.site_url = _derive_site_url(base_url)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds)),
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def page_url(self, title: str) -> str:
        """Return the public article URL for a page title."""
        if not title:
            return self.site_url
        return f"{self.site_url}/{quote(title.replace(' ', '_'), safe='')}"

    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "format": "json",
            "formatversion": 2,
            "utf8": 1,
            **params,
        }
        try:
            response = await self._client.get(self.base_url, params=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            return {"error": "timeout", "detail": "VCPedia request timed out"}
        except httpx.HTTPStatusError as exc:
            return {
                "error": "http error",
                "detail": f"HTTP {exc.response.status_code}",
            }
        except httpx.HTTPError as exc:
            return {"error": "request failed", "detail": str(exc)}
        except ValueError:
            return {
                "error": "invalid response",
                "detail": "VCPedia returned non-JSON data",
            }

        if isinstance(data, dict) and data.get("error"):
            return {"error": "api error", "detail": data["error"]}
        return data

    async def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        """Search article pages and return raw API data."""
        return await self._request(
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": max(1, min(limit, 20)),
                "srnamespace": 0,
                "srprop": "snippet",
            }
        )

    async def get_pages(
        self,
        titles: list[str],
        with_extracts: bool = True,
    ) -> dict[str, Any]:
        """Fetch wikitext, categories, metadata, and optional intro extracts."""
        cleaned_titles = [title.strip() for title in titles if title and title.strip()]
        if not cleaned_titles:
            return {"error": "empty titles", "pages": []}

        props = ["revisions", "categories", "info"]
        params: dict[str, Any] = {
            "action": "query",
            "prop": "|".join(props + (["extracts"] if with_extracts else [])),
            "titles": "|".join(cleaned_titles[:20]),
            "redirects": 1,
            "rvslots": "main",
            "rvprop": "content",
            "cllimit": "max",
            "inprop": "url",
        }
        if with_extracts:
            params.update(
                {
                    "exintro": 1,
                    "explaintext": 1,
                    "exlimit": "max",
                    "exchars": 2000,
                }
            )

        data = await self._request(params)
        if data.get("error"):
            return {
                "error": data.get("error"),
                "detail": data.get("detail", ""),
                "pages": [],
            }

        query = data.get("query") or {}
        pages = _normalize_pages(query.get("pages"))
        normalized: list[dict[str, Any]] = []
        for page in pages:
            categories = []
            for category in page.get("categories") or []:
                name = (
                    category.get("title", "")
                    if isinstance(category, dict)
                    else str(category)
                )
                if name:
                    categories.append(name.removeprefix("Category:"))

            normalized.append(
                {
                    "title": page.get("title", ""),
                    "pageid": page.get("pageid"),
                    "missing": bool(page.get("missing")),
                    "fullurl": page.get("fullurl", ""),
                    "extract": page.get("extract", ""),
                    "categories": categories,
                    "length": page.get("length", 0),
                    "touched": page.get("touched", ""),
                    "redirect": bool(page.get("redirect")),
                    "wikitext": _extract_content(page),
                }
            )

        return {
            "pages": normalized,
            "redirects": query.get("redirects", []),
        }
