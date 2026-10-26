"""AstrBot entry point for the VCPedia query plugin."""

from __future__ import annotations

import inspect
import json
import re
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

try:
    from .vcpedia.config import VCPediaConfig
    from .vcpedia.tools import (
        get_full_page,
        get_lyrics,
        get_page_info,
        get_page_section,
        get_wiki_summary,
        search_wiki_page,
    )
    from .vcpedia.tools.resolve import normalize_query_text
    from .vcpedia.wiki.api import VCPediaAPI
    from .vcpedia.wiki.cache import WikiTTLCache
except ImportError:
    from vcpedia.config import VCPediaConfig
    from vcpedia.tools import (
        get_full_page,
        get_lyrics,
        get_page_info,
        get_page_section,
        get_wiki_summary,
        search_wiki_page,
    )
    from vcpedia.tools.resolve import normalize_query_text
    from vcpedia.wiki.api import VCPediaAPI
    from vcpedia.wiki.cache import WikiTTLCache


VCPEDIA_TOOL_PROMPT = """
回答虚拟歌手、VOCALOID、Synthesizer V、ACE Studio、中文原创曲、P主、声库、专辑相关问题时，优先调用 ask_vcpedia（统一工具入口）。

规则：
1. 默认只调用 ask_vcpedia，避免在多个工具之间反复试错。
2. 歌曲信息（演唱、UP主、投稿时间、播放量、STAFF、成就）用 mode=song；只要歌词用 mode=lyrics。
3. P主/创作者用 mode=producer；虚拟歌手/声库/角色用 mode=voicebank；专辑用 mode=album；不确定页面名先 mode=search。
4. 回答使用中文，先给结论，再给关键细节；引用歌词时只引用与问题相关的短句，并注明来自 VCPedia。
5. 返回结果里的 url 是 VCPedia 页面链接，回答时可以附上。
6. 如果 error=page not found，请明确告知未找到页面，并给出可重试的关键词。
""".strip()


SECTION_NAMES = (
    "staff的话",
    "staff附言",
    "收录曲目",
    "二次创作",
    "外部链接",
    "歌词",
    "歌詞",
    "简介",
    "歌曲",
    "曲目",
    "杂谈",
    "注释",
)
SECTION_FIRST_RE = re.compile(
    r"^(?:(?:查询|查一下|查看|看看|查)\s*)?("
    + "|".join(re.escape(name) for name in SECTION_NAMES)
    + r")\s*[:：]\s*(.+)$",
    re.IGNORECASE,
)
SECTION_LAST_RE = re.compile(
    r"^(.+?)的("
    + "|".join(re.escape(name) for name in SECTION_NAMES)
    + r")(?:是什么|有哪些|内容|部分)?$",
    re.IGNORECASE,
)

MODE_ALIASES = {
    "auto": "auto",
    "summary": "summary",
    "摘要": "summary",
    "search": "search",
    "搜索": "search",
    "info": "info",
    "entity": "info",
    "页面": "info",
    "song": "song",
    "歌曲": "song",
    "lyrics": "lyrics",
    "lyric": "lyrics",
    "歌词": "lyrics",
    "producer": "producer",
    "p主": "producer",
    "creator": "producer",
    "voicebank": "voicebank",
    "vocal": "voicebank",
    "singer": "voicebank",
    "虚拟歌手": "voicebank",
    "album": "album",
    "专辑": "album",
    "section": "section",
    "章节": "section",
    "full_page": "full_page",
    "fullpage": "full_page",
    "full-page": "full_page",
    "full": "full_page",
    "page": "full_page",
}

VALID_MODES = {
    "auto",
    "summary",
    "search",
    "info",
    "song",
    "lyrics",
    "producer",
    "voicebank",
    "album",
    "section",
    "full_page",
}


def _to_json(payload: dict[str, Any], max_chars: int = 3800) -> str:
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    preview = text[: max(0, max_chars - 160)]
    return json.dumps(
        {"truncated": True, "note": "payload too large", "preview": preview},
        ensure_ascii=False,
    )


def _normalize_mode(mode: str) -> str:
    text = (mode or "auto").strip().casefold()
    return MODE_ALIASES.get(text, text)


def _infer_intent(question: str) -> str:
    text = (question or "").casefold()
    if any(keyword in text for keyword in ("歌词", "歌詞", "唱词")):
        return "lyrics"
    if any(keyword in text for keyword in ("全文", "整页", "完整页面", "完整内容")):
        return "full_page"
    if any(
        keyword in text for keyword in ("专辑", "專輯", "唱片", "收录", "收錄", "曲目")
    ):
        return "album"
    if any(
        keyword in text
        for keyword in (
            "p主",
            "p 主",
            "创作者",
            "up主",
            "作者是谁",
            "作曲是谁",
            "作词是谁",
        )
    ):
        return "producer"
    if any(
        keyword in text
        for keyword in ("虚拟歌手", "虚拟歌姬", "声库", "声源", "音源", "歌姬", "角色")
    ):
        return "voicebank"
    if any(
        keyword in text
        for keyword in (
            "歌曲",
            "谁唱的",
            "演唱",
            "投稿",
            "播放",
            "staff",
            "制作人员",
            "殿堂",
            "传说曲",
            "神话曲",
        )
    ):
        return "song"
    if any(
        keyword in text
        for keyword in ("章节", "部分", "历史", "争议", "评价", "二次创作", "杂谈")
    ):
        return "section"
    return "info"


def _extract_section_query(question: str) -> tuple[str, str]:
    text = (question or "").strip()
    if not text:
        return "", ""

    first = SECTION_FIRST_RE.match(text)
    if first:
        return first.group(2).strip(), first.group(1).strip()

    last = SECTION_LAST_RE.match(text)
    if last:
        return last.group(1).strip(), last.group(2).strip()

    return text, ""


@register(
    "astrbot_plugin_vcpedia",
    "Proj-QQBot",
    "LLM 可调用的 VCPedia 虚拟歌手百科查询插件",
    "v1.0.0",
)
class VCPediaPlugin(Star):
    """VCPedia query plugin exposed to AstrBot's LLM tool system."""

    def __init__(self, context: Context, config: Any | None = None):
        super().__init__(context)
        self.config = VCPediaConfig.from_mapping(config)
        self.api = VCPediaAPI(
            base_url=self.config.base_url,
            timeout_seconds=self.config.timeout_seconds,
            user_agent=self.config.user_agent,
        )
        self.cache = WikiTTLCache(ttl_seconds=self.config.cache_ttl_seconds)

    async def initialize(self) -> None:
        add_prompt = getattr(self.context, "add_system_prompt", None)
        if callable(add_prompt):
            prompt_result = add_prompt(VCPEDIA_TOOL_PROMPT)
            if inspect.isawaitable(prompt_result):
                await prompt_result
        logger.info("vcpedia tools registered")

    async def _dispatch(
        self,
        question: str,
        mode: str,
        section: str,
    ) -> tuple[str, dict[str, Any]]:
        raw_question = (question or "").strip()
        if not raw_question:
            return "", {"error": "empty query"}

        resolved_mode = _normalize_mode(mode)
        if resolved_mode == "auto":
            resolved_mode = _infer_intent(raw_question)
        if resolved_mode not in VALID_MODES or resolved_mode == "auto":
            return "", {
                "error": "unknown mode",
                "mode": mode,
                "valid_modes": sorted(VALID_MODES),
            }

        if resolved_mode == "section":
            title_query, section_guess = _extract_section_query(raw_question)
            query = normalize_query_text(title_query) or title_query
            target_section = section.strip() or section_guess
            if not target_section:
                lowered = raw_question.casefold()
                target_section = next(
                    (name for name in SECTION_NAMES if name in lowered), ""
                )
            result = await get_page_section(
                self.api,
                self.cache,
                query,
                target_section,
                max_chars=self.config.max_return_chars,
            )
            return "get_page_section", result

        query = normalize_query_text(raw_question) or raw_question

        if resolved_mode == "search":
            result = await search_wiki_page(
                self.api,
                query,
                limit=self.config.default_search_limit,
                cache=self.cache,
            )
            return "search_wiki_page", result

        if resolved_mode == "summary":
            result = await get_wiki_summary(
                self.api,
                self.cache,
                query,
                max_chars=min(1200, self.config.max_return_chars),
            )
            return "get_wiki_summary", result

        if resolved_mode == "song":
            result = await get_page_info(
                self.api,
                self.cache,
                query,
                preferred_type="song",
                include_lyrics_excerpt=True,
                max_chars=self.config.max_return_chars,
            )
            return "get_song_info", result

        if resolved_mode in {"producer", "voicebank", "album", "info"}:
            preferred_type = None if resolved_mode == "info" else resolved_mode
            result = await get_page_info(
                self.api,
                self.cache,
                query,
                preferred_type=preferred_type,
                include_lyrics_excerpt=False,
                max_chars=self.config.max_return_chars,
            )
            return "get_page_info", result

        if resolved_mode == "lyrics":
            result = await get_lyrics(
                self.api,
                self.cache,
                query,
                max_chars=self.config.max_lyrics_chars,
            )
            return "get_lyrics", result

        result = await get_full_page(
            self.api,
            self.cache,
            query,
            max_chars=self.config.max_full_page_chars,
        )
        return "get_full_page", result

    @filter.llm_tool(name="ask_vcpedia")
    async def llm_ask_vcpedia(
        self,
        event: AstrMessageEvent,
        question: str,
        mode: str = "auto",
        section: str = "",
    ) -> str:
        """查询 VCPedia（虚拟歌手百科），推荐给 LLM 的统一工具入口。

        Args:
            question(string): 用户问题或关键词，例如“权御天下的歌词”“ilem的生日”“洛天依是谁”
            mode(string): 查询模式，支持 auto/summary/search/info/song/lyrics/producer/voicebank/album/section/full_page
            section(string): section 模式下的章节名，例如 简介、歌词、收录曲目；留空则从问题中推断
        """
        try:
            tool_used, result = await self._dispatch(question, mode, section)
        except Exception as exc:
            logger.exception("vcpedia query failed")
            return _to_json({"error": "internal error", "detail": str(exc)})

        if not tool_used:
            return _to_json(result, max_chars=self.config.max_return_chars)

        payload = {
            "intent": _normalize_mode(mode),
            "tool_used": tool_used,
            "result": result,
        }
        if payload["intent"] == "auto":
            payload["intent"] = _infer_intent(question)

        if tool_used == "get_full_page":
            max_chars = max(
                self.config.max_return_chars, self.config.max_full_page_chars + 2000
            )
        elif tool_used == "get_lyrics":
            max_chars = max(
                self.config.max_return_chars, self.config.max_lyrics_chars + 1500
            )
        else:
            max_chars = self.config.max_return_chars
        return _to_json(payload, max_chars=max_chars)

    @filter.llm_tool(name="search_vcpedia_page")
    async def llm_search_vcpedia_page(self, event: AstrMessageEvent, query: str) -> str:
        """搜索 VCPedia 页面。

        Args:
            query(string): 搜索词，优先使用中文歌名、P主名或虚拟歌手名
        """
        result = await search_wiki_page(
            self.api,
            query,
            limit=self.config.default_search_limit,
            cache=self.cache,
        )
        return _to_json(result, max_chars=self.config.max_return_chars)

    @filter.llm_tool(name="get_vcpedia_summary")
    async def llm_get_vcpedia_summary(self, event: AstrMessageEvent, title: str) -> str:
        """获取 VCPedia 页面的摘要。

        Args:
            title(string): 页面标题或关键词
        """
        result = await get_wiki_summary(
            self.api,
            self.cache,
            title,
            max_chars=min(1200, self.config.max_return_chars),
        )
        return _to_json(result, max_chars=self.config.max_return_chars)

    @filter.llm_tool(name="get_vcpedia_page_info")
    async def llm_get_vcpedia_page_info(
        self,
        event: AstrMessageEvent,
        title: str,
        info_type: str = "auto",
    ) -> str:
        """获取 VCPedia 页面的结构化信息（信息框、摘要、章节、STAFF 等）。

        Args:
            title(string): 页面标题或关键词
            info_type(string): 页面类型偏好，支持 auto/song/producer/voicebank/album
        """
        preferred_type = _normalize_mode(info_type)
        if preferred_type in {"auto", "info"}:
            preferred_type = None
        elif preferred_type not in {"song", "producer", "voicebank", "album"}:
            preferred_type = None
        result = await get_page_info(
            self.api,
            self.cache,
            title,
            preferred_type=preferred_type,
            include_lyrics_excerpt=(preferred_type == "song"),
            max_chars=self.config.max_return_chars,
        )
        return _to_json(result, max_chars=self.config.max_return_chars)

    @filter.llm_tool(name="get_vcpedia_song_info")
    async def llm_get_vcpedia_song_info(
        self, event: AstrMessageEvent, song: str
    ) -> str:
        """获取 VCPedia 歌曲信息（演唱、UP主、投稿时间、STAFF、成就等）。

        Args:
            song(string): 歌曲名或“歌曲名(演唱者)”
        """
        result = await get_page_info(
            self.api,
            self.cache,
            song,
            preferred_type="song",
            include_lyrics_excerpt=True,
            max_chars=self.config.max_return_chars,
        )
        return _to_json(result, max_chars=self.config.max_return_chars)

    @filter.llm_tool(name="get_vcpedia_lyrics")
    async def llm_get_vcpedia_lyrics(self, event: AstrMessageEvent, song: str) -> str:
        """获取 VCPedia 歌曲页面的歌词。

        Args:
            song(string): 歌曲名或“歌曲名(演唱者)”
        """
        result = await get_lyrics(
            self.api,
            self.cache,
            song,
            max_chars=self.config.max_lyrics_chars,
        )
        max_chars = max(
            self.config.max_return_chars, self.config.max_lyrics_chars + 1500
        )
        return _to_json(result, max_chars=max_chars)

    @filter.llm_tool(name="get_vcpedia_section")
    async def llm_get_vcpedia_section(
        self,
        event: AstrMessageEvent,
        title: str,
        section: str,
    ) -> str:
        """获取 VCPedia 页面的指定章节。

        Args:
            title(string): 页面标题或关键词
            section(string): 章节名，例如 简介、歌词、收录曲目、杂谈
        """
        result = await get_page_section(
            self.api,
            self.cache,
            title,
            section,
            max_chars=self.config.max_return_chars,
        )
        return _to_json(result, max_chars=self.config.max_return_chars)

    async def terminate(self) -> None:
        await self.api.close()


__all__ = ["VCPediaPlugin"]
