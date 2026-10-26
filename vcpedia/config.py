"""Configuration model for the VCPedia plugin."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _safe_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


@dataclass
class VCPediaConfig:
    """Runtime settings shared by every tool in the plugin."""

    base_url: str = "https://vcpedia.cn/api.php"
    timeout_seconds: float = 12.0
    cache_ttl_seconds: int = 24 * 60 * 60
    max_return_chars: int = 3800
    max_full_page_chars: int = 16000
    max_lyrics_chars: int = 6000
    default_search_limit: int = 5
    user_agent: str = "astrbot-plugin-vcpedia/1.0"

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any] | Any | None) -> VCPediaConfig:
        """Build a config from AstrBot's mapping-like config object.

        Args:
            config: AstrBot plugin config, a plain mapping, or None.

        Returns:
            A validated configuration instance.
        """
        if config is None:
            return cls()

        getter = getattr(config, "get", None)
        if not callable(getter):
            return cls()

        return cls(
            base_url=_safe_str(getter("base_url", cls.base_url), cls.base_url),
            timeout_seconds=_safe_float(
                getter("timeout_seconds", cls.timeout_seconds),
                cls.timeout_seconds,
            ),
            cache_ttl_seconds=_safe_int(
                getter("cache_ttl_seconds", cls.cache_ttl_seconds),
                cls.cache_ttl_seconds,
            ),
            max_return_chars=_safe_int(
                getter("max_return_chars", cls.max_return_chars),
                cls.max_return_chars,
            ),
            max_full_page_chars=_safe_int(
                getter("max_full_page_chars", cls.max_full_page_chars),
                cls.max_full_page_chars,
            ),
            max_lyrics_chars=_safe_int(
                getter("max_lyrics_chars", cls.max_lyrics_chars),
                cls.max_lyrics_chars,
            ),
            default_search_limit=_safe_int(
                getter("default_search_limit", cls.default_search_limit),
                cls.default_search_limit,
            ),
            user_agent=_safe_str(getter("user_agent", cls.user_agent), cls.user_agent),
        )
