"""Wikitext parsing helpers tailored to VCPedia article pages.

VCPedia articles are template-heavy: song pages use ``VOCALOID_Songbox``,
producer pages use ``Producer``, voicebank pages use ``人物信息``, and album
pages use ``Album Infobox``.  Multi-version songs are often wrapped in
``tabs/core``, so rendering has to expand tab bodies before headings can be
split into sections.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

REDIRECT_RE = re.compile(
    r"^\s*#(?:redirect|重定向)\s*\[\[([^\]]+)\]\]", re.IGNORECASE | re.MULTILINE
)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
REF_RE = re.compile(r"<ref\b[^>]*>.*?</ref>", re.IGNORECASE | re.DOTALL)
REF_SELF_RE = re.compile(r"<ref\b[^>]*/\s*>", re.IGNORECASE)
EMBED_RE = re.compile(
    r"<(gallery|timeline|score|math|syntaxhighlight|source|imagemap)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
SECTION_LINE_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")

INFOBOX_SPECS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("vocaloid songbox", "songbox", "歌曲信息", "歌曲信息框"), "song"),
    (("producer", "p主信息", "创作者信息"), "producer"),
    (("人物信息", "虚拟歌手信息", "角色信息"), "voicebank"),
    (("album infobox", "专辑信息", "專輯信息"), "album"),
)

SKIP_FIELD_KEYS = {
    "image",
    "图片",
    "图片信息",
    "图片说明",
    "图像",
    "图像信息",
    "颜色",
    "颜色1",
    "颜色2",
    "颜色3",
    "color",
    "colour",
    "标题颜色",
    "标题字体颜色",
    "左栏颜色",
    "左栏字体颜色",
    "表格颜色",
    "背景颜色",
    "style",
    "width",
    "宽",
    "分类",
    "nocat",
    "年表",
}

DROP_TEMPLATES = {
    "about",
    "otheruses",
    "otheruseslist",
    "for",
    "redirect",
    "anchor",
    "锚点",
    "disambig",
    "消歧义",
    "消歧义页",
    "hatnote",
    "main",
    "主条目",
    "see also",
    "参见",
    "details",
    "further",
    "标题格式化",
    "标题替换",
    "小写标题",
    "大写标题",
    "customtop",
    "生日祝福",
    "navbox",
    "navbox subgroup",
    "navigation",
    "导航框",
    "导航",
    "音乐专辑",
    "音乐专辑导航",
    "familytree",
    "chart",
    "dpl",
    "dynamicpagelist",
    "reflist",
    "references",
    "notelist",
    "clear",
    "infobox",
    "信息框",
    "人物信息",
    "producer",
    "vocaloid songbox",
    "album infobox",
    "songbox",
    "歌曲信息",
    "歌曲信息框",
    "p主信息",
    "创作者信息",
    "虚拟歌手信息",
    "角色信息",
    "专辑信息",
    "專輯信息",
    "toc",
    "toc limit",
    "quote box",
    "bilibilicount",
    "bilibili video",
    "bilibilivideo",
    "youtube",
    "youtube count",
    "cite",
    "cite web",
    "cite news",
    "cite book",
    "cite journal",
    "cite episode",
    "cite av media",
    "cite tweet",
    "cite video",
    "cite interview",
    "cite magazine",
    "cite press release",
    "cite thesis",
}

DROP_PREFIXES = (
    "navbox",
    "小导航条",
    "infobox",
    "vocaloid songbox",
    "album infobox",
    "cite ",
    "bilibili",
    "youtube",
    "dynamicpagelist",
    "#invoke",
    "#tag",
)

COLLAPSE_FLAGS = {
    "collapsed",
    "uncollapsed",
    "open",
    "close",
    "hide",
    "hidden",
    "yes",
    "no",
    "true",
    "false",
}

PASS_LAST_TEMPLATES = {
    "color",
    "fontcolor",
    "文字颜色",
    "字体颜色",
    "黑幕",
    "删除线",
    "del",
    "s",
    "strike",
    "center",
    "left",
    "right",
    "small",
    "big",
    "large",
    "nowrap",
    "lang",
    "lj",
    "注",
    "注释",
    "标记",
    "lyrics",
    "歌词",
}

PASS_FIRST_TEMPLATES = {
    "ruby",
    "coloredlink",
    "文字描边",
    "文字描边2",
    "tooltip",
    "abbr",
    "link",
    "cquote",
    "quote",
    "blockquote",
    "引用",
    "引文",
    "photrans",
    "poem",
    "u",
    "underline",
    "s",
    "strike",
}

ASTROLOGY_RANGES = (
    ((3, 21), (4, 19), "白羊座"),
    ((4, 20), (5, 20), "金牛座"),
    ((5, 21), (6, 21), "双子座"),
    ((6, 22), (7, 22), "巨蟹座"),
    ((7, 23), (8, 22), "狮子座"),
    ((8, 23), (9, 22), "处女座"),
    ((9, 23), (10, 23), "天秤座"),
    ((10, 24), (11, 22), "天蝎座"),
    ((11, 23), (12, 21), "射手座"),
    ((12, 22), (1, 19), "摩羯座"),
    ((1, 20), (2, 18), "水瓶座"),
    ((2, 19), (3, 20), "双鱼座"),
)


@dataclass
class Template:
    """A parsed MediaWiki template invocation."""

    name: str
    params: dict[str, str]
    positional: list[str]
    raw: str


def limit_text(text: str, max_chars: int = 6000) -> str:
    """Trim text to a maximum length, adding an ellipsis when needed."""
    text = (text or "").strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def strip_html(text: str) -> str:
    """Remove HTML tags and entities from MediaWiki snippets."""
    no_tag = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(re.sub(r"\s+", " ", no_tag)).strip()


def normalize_title_for_match(title: str) -> str:
    """Normalize a page title for case- and punctuation-insensitive matching."""
    text = html.unescape(title or "").replace("_", " ")
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def title_variants(title: str) -> list[str]:
    """Return common title spellings (full-width vs ASCII parentheses)."""
    base = (title or "").strip()
    if not base:
        return []

    variants = [base]
    if "（" in base or "）" in base:
        variants.append(base.replace("（", "(").replace("）", ")"))
    if "(" in base or ")" in base:
        variants.append(base.replace("(", "（").replace(")", "）"))
    variants.append(base.replace("_", " "))
    variants.append(base.replace(" ", "_"))

    deduped: list[str] = []
    for variant in variants:
        variant = variant.strip()
        if variant and variant not in deduped:
            deduped.append(variant)
    return deduped


def resolve_redirect_title(wikitext: str) -> str:
    """Extract a redirect target from raw wikitext, if present."""
    match = REDIRECT_RE.search(wikitext or "")
    return match.group(1).strip() if match else ""


def _template_end(text: str, start: int) -> int:
    """Return the index just after the matching ``}}`` for a template."""
    depth = 0
    index = start
    length = len(text)
    while index < length - 1:
        if text.startswith("{{", index):
            if index + 2 < length and text[index + 2] == "{":
                depth += 1
                index += 3
            else:
                depth += 1
                index += 2
            continue
        if text.startswith("}}", index):
            if index + 2 < length and text[index + 2] == "}":
                depth -= 1
                index += 3
            else:
                depth -= 1
                index += 2
            if depth <= 0:
                return index
            continue
        index += 1
    return -1


def iter_templates(text: str) -> Iterable[tuple[str, int, int]]:
    """Yield top-level template spans as ``(raw, start, end)``."""
    index = 0
    length = len(text)
    while index < length - 1:
        if text.startswith("{{", index):
            end = _template_end(text, index)
            if end == -1:
                return
            yield text[index:end], index, end
            index = end
        else:
            index += 1


def _split_top_level(text: str, separator: str = "|") -> list[str]:
    """Split on a separator while ignoring nested templates and links."""
    parts: list[str] = []
    buffer: list[str] = []
    curly = 0
    link = 0
    index = 0
    while index < len(text):
        if text.startswith("{{", index):
            curly += 1
            buffer.append("{{")
            index += 2
            continue
        if text.startswith("}}", index) and curly:
            curly -= 1
            buffer.append("}}")
            index += 2
            continue
        if text.startswith("[[", index):
            link += 1
            buffer.append("[[")
            index += 2
            continue
        if text.startswith("]]", index) and link:
            link -= 1
            buffer.append("]]")
            index += 2
            continue

        char = text[index]
        if char == separator and curly == 0 and link == 0:
            parts.append("".join(buffer))
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1

    parts.append("".join(buffer))
    return parts


def _split_param(part: str) -> tuple[str, str] | None:
    """Split a named template parameter at its first top-level ``=``."""
    curly = 0
    link = 0
    index = 0
    while index < len(part):
        if part.startswith("{{", index):
            curly += 1
            index += 2
            continue
        if part.startswith("}}", index) and curly:
            curly -= 1
            index += 2
            continue
        if part.startswith("[[", index):
            link += 1
            index += 2
            continue
        if part.startswith("]]", index) and link:
            link -= 1
            index += 2
            continue
        if part[index] == "=" and curly == 0 and link == 0:
            key = part[:index].strip()
            if not key:
                return None
            return key, part[index + 1 :].strip()
        index += 1
    return None


def parse_template(raw: str) -> Template:
    """Parse a raw template invocation into name, named params and positionals."""
    body = raw[2:-2] if raw.startswith("{{") and raw.endswith("}}") else raw
    parts = _split_top_level(body)
    name = parts[0].strip() if parts else ""
    params: dict[str, str] = {}
    positional: list[str] = []

    for part in parts[1:]:
        pair = _split_param(part)
        if pair is None:
            positional.append(part.strip())
        else:
            key, value = pair
            params[key] = value

    return Template(name=name, params=params, positional=positional, raw=raw)


def normalize_template_name(name: str) -> str:
    """Normalize a template name for comparisons."""
    text = (name or "").strip()
    text = re.sub(r"^(?:subst|safesubst)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^template\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _name_pattern(name: str) -> str:
    escaped = re.escape(name)
    return escaped.replace(r"\ ", "[ _]")


def find_named_templates(wikitext: str, names: Iterable[str]) -> list[Template]:
    """Find template invocations by name, including ones nested in tabs."""
    patterns = [_name_pattern(name) for name in names if name]
    if not patterns:
        return []

    regex = re.compile(
        r"\{\{\s*(?:Template\s*:\s*)?"
        + "(?:"
        + "|".join(patterns)
        + r")\s*(?=\||\}\})",
        re.IGNORECASE,
    )
    found: list[Template] = []
    seen_starts: set[int] = set()
    for match in regex.finditer(wikitext or ""):
        start = match.start()
        if start in seen_starts:
            continue
        end = _template_end(wikitext, start)
        if end == -1:
            continue
        seen_starts.add(start)
        found.append(parse_template(wikitext[start:end]))
    return found


def _parse_age_args(positional: list[str]) -> str:
    numbers = [part.strip() for part in positional[:3]]
    if len(numbers) < 3:
        return ""
    try:
        year, month, day = (int(value) for value in numbers)
    except ValueError:
        return ""
    today = date.today()
    age = today.year - year - ((today.month, today.day) < (month, day))
    return f"{age}岁" if age >= 0 else ""


def _parse_astrology_args(positional: list[str]) -> str:
    if len(positional) < 2:
        return ""
    try:
        month, day = int(positional[0].strip()), int(positional[1].strip())
    except ValueError:
        return ""
    for (start_month, start_day), (end_month, end_day), sign in ASTROLOGY_RANGES:
        if (start_month, start_day) <= (month, day) <= (end_month, end_day):
            return sign
    return ""


def _convert_language_variant(inner: str) -> str:
    if ":" not in inner:
        return inner
    parts = [part.strip() for part in inner.split(";") if part.strip()]
    mapping: dict[str, str] = {}
    for part in parts:
        if ":" in part:
            key, value = part.split(":", 1)
            mapping[key.strip().casefold()] = value.strip()
    for key in ("zh-hans", "zh-cn", "zh", "zh-hant", "zh-tw", "zh-hk"):
        if key in mapping:
            return mapping[key]
    return parts[0].split(":", 1)[-1] if parts else inner


TRACK_FIELD_LABELS = (
    ("singer", "演唱"),
    ("lyrics", "作词"),
    ("music", "作曲"),
    ("extra", "调校"),
    ("length", "时长"),
)


def _tracklist_rows(template: Template) -> tuple[list[dict[str, Any]], str]:
    """Parse numbered ``Tracklist`` parameters into rows."""
    params = {key.strip().casefold(): value for key, value in template.params.items()}
    indices: set[int] = set()
    for key in params:
        match = re.fullmatch(r"(?:title|lyrics|music|singer|extra|length)(\d+)", key)
        if match:
            indices.add(int(match.group(1)))

    rows: list[dict[str, Any]] = []
    for index in sorted(indices):
        title = params.get(f"title{index}", "").strip()
        if not title:
            continue
        row: dict[str, Any] = {"index": index, "title": title}
        for field in ("lyrics", "music", "singer", "extra", "length"):
            value = params.get(f"{field}{index}", "").strip()
            if value:
                row[field] = value
        rows.append(row)

    return rows, params.get("extra_column", "").strip() or "备注"


def _render_tracklist(template: Template, depth: int, ruby_annotation: bool) -> str:
    rows, extra_label = _tracklist_rows(template)
    lines: list[str] = []
    for row in rows:
        title = _expand_templates(row["title"], depth, ruby_annotation)
        details: list[str] = []
        for field, label in TRACK_FIELD_LABELS:
            value = row.get(field)
            if not value:
                continue
            if field == "extra":
                label = extra_label
            details.append(
                f"{label}：{_expand_templates(value, depth, ruby_annotation)}"
            )
        line = f"{row['index']}. {title}"
        if details:
            line += "（" + "；".join(details) + "）"
        lines.append(line)
    return "\n".join(lines)


def _render_template(raw: str, depth: int, ruby_annotation: bool) -> str:
    template = parse_template(raw)
    name = normalize_template_name(template.name)
    if not name:
        return ""

    if name in {"bilibilicount", "bilibili count"}:
        return "（B站数据）"
    if name in {"bilibilivideo", "bilibili video"}:
        video_id = template.params.get("id", "").strip()
        if not video_id:
            return ""
        if video_id.isdigit():
            video_id = f"av{video_id}"
        return f"（B站视频：https://www.bilibili.com/video/{video_id}）"

    if name in DROP_TEMPLATES or name.startswith(DROP_PREFIXES) or "题头" in name:
        return ""

    if name == "tracklist":
        return _render_tracklist(template, depth, ruby_annotation)

    if name in {"tabs/core", "tabs", "tab", "tabber"}:
        tab_values: list[tuple[int, str]] = []
        for key, value in template.params.items():
            match = re.fullmatch(r"text(\d+)", key.strip(), re.IGNORECASE)
            if match:
                tab_values.append((int(match.group(1)), value))
        if not tab_values and "text" in template.params:
            tab_values.append((1, template.params["text"]))
        tab_values.sort(key=lambda item: item[0])
        return "\n".join(
            _expand_templates(value, depth, ruby_annotation) for _, value in tab_values
        )

    if name == "ruby":
        base = (
            template.positional[0]
            if template.positional
            else template.params.get("1", "")
        )
        reading = template.positional[1] if len(template.positional) > 1 else ""
        base_text = _expand_templates(base, depth, ruby_annotation).strip()
        reading_text = _expand_templates(reading, depth, ruby_annotation).strip()
        if base_text and reading_text and ruby_annotation:
            return f"{base_text}（{reading_text}）"
        return base_text

    if name == "coloredlink":
        value = template.positional[1] if len(template.positional) > 1 else ""
        if not value:
            value = template.params.get("2", "")
        return _expand_templates(value, depth, ruby_annotation)

    if name == "age":
        return _parse_age_args(template.positional)
    if name == "astrology":
        return _parse_astrology_args(template.positional)
    if name in {"date", "birthday"}:
        if len(template.positional) < 3:
            return ""
        year, month, day = template.positional[:3]
        return f"{year}年{month}月{day}日"

    if name in PASS_LAST_TEMPLATES:
        value = template.positional[-1] if template.positional else ""
        if not value:
            for key in ("text", "content", "内容", "1"):
                if template.params.get(key):
                    value = template.params[key]
                    break
        return _expand_templates(value, depth, ruby_annotation)

    if name in PASS_FIRST_TEMPLATES:
        value = template.positional[0] if template.positional else ""
        if not value:
            for key in ("text", "content", "内容", "1"):
                if template.params.get(key):
                    value = template.params[key]
                    break
        return _expand_templates(value, depth, ruby_annotation)

    for key in ("text", "content", "内容", "文本", "1"):
        if template.params.get(key):
            return _expand_templates(template.params[key], depth, ruby_annotation)

    if template.positional:
        value = template.positional[-1].strip()
        if len(template.positional) == 1 and value.casefold() in COLLAPSE_FLAGS:
            return ""
        return _expand_templates(value, depth, ruby_annotation)

    return ""


def _expand_templates(text: str, depth: int = 0, ruby_annotation: bool = False) -> str:
    if not text or depth > 8:
        return ""
    text = COMMENT_RE.sub("", text)
    text = REF_RE.sub("", text)
    text = REF_SELF_RE.sub("", text)
    text = EMBED_RE.sub("", text)

    output: list[str] = []
    position = 0
    for raw, start, end in iter_templates(text):
        output.append(text[position:start])
        output.append(_render_template(raw, depth + 1, ruby_annotation))
        position = end
    output.append(text[position:])
    return "".join(output)


def _strip_table_cell_attributes(body: str) -> str:
    return re.sub(
        r'^(?:(?:style|class|scope|rowspan|colspan|align|width|height|bgcolor|id)\s*=\s*(?:"[^"]*"|\'[^\']*\')\s*\|)+',
        "",
        body,
        flags=re.IGNORECASE,
    )


def _clean_table_markup(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if (
            stripped.startswith("{|")
            or stripped.startswith("|}")
            or stripped.startswith("|-")
        ):
            continue
        if stripped.startswith("|+"):
            lines.append(stripped[2:].strip())
            continue
        if stripped.startswith("!") or stripped.startswith("|"):
            body = _strip_table_cell_attributes(stripped[1:].strip())
            separator = "!!" if stripped.startswith("!") else "||"
            cells = [cell.strip() for cell in body.split(separator)]
            lines.append(" | ".join(cell for cell in cells if cell))
            continue
        lines.append(line)
    return "\n".join(lines)


def _clean_markup(text: str, inline: bool = False) -> str:
    text = re.sub(
        r"\[\[\s*(?:File|Image|文件|图像|分类|Category)\s*:[^\]]*\]\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", lambda match: match.group(2), text)
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda match: match.group(1).split("#")[0], text)
    text = re.sub(
        r"\[(https?://[^\s\]]+)\s+([^\]]+)\]", lambda match: match.group(2), text
    )
    text = re.sub(r"\[(https?://[^\s\]]+)\]", "", text)

    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<hr\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</(?:p|div|poem|center|blockquote|ul|ol|table|tr|h[1-6])\s*>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<t[dh][^>]*>", " | ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)

    text = re.sub(r"__[A-Z]+__", "", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(
        r"-\{([^{}]*)\}-", lambda match: _convert_language_variant(match.group(1)), text
    )
    text = re.sub(r"^----+\s*$", "", text, flags=re.MULTILINE)

    if not inline:
        text = _clean_table_markup(text)
        # List markers must be converted before headings, otherwise ``## 标题``
        # would be mistaken for a numbered list item.
        text = re.sub(
            r"^(\*+)\s*",
            lambda match: "  " * (len(match.group(1)) - 1) + "- ",
            text,
            flags=re.MULTILINE,
        )
        text = re.sub(
            r"^(\#+)\s*",
            lambda match: "  " * (len(match.group(1)) - 1) + "1. ",
            text,
            flags=re.MULTILINE,
        )
        text = re.sub(r"^([;:])\s*", "- ", text, flags=re.MULTILINE)
        text = re.sub(
            r"^(={2,6})\s*(.*?)\s*\1\s*$",
            lambda match: "#" * len(match.group(1)) + " " + match.group(2).strip(),
            text,
            flags=re.MULTILINE,
        )

    text = re.sub(r"[ \t]+", " ", text)
    if inline:
        text = re.sub(r"\s*\n+\s*", " / ", text)
    else:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


def render_wikitext(wikitext: str) -> str:
    """Render article wikitext to readable plain text with ``##`` headings."""
    expanded = _expand_templates(wikitext or "")
    return _clean_markup(expanded, inline=False)


def render_inline(value: str, ruby_annotation: bool = True) -> str:
    """Render a template parameter value as a single readable line."""
    expanded = _expand_templates(value or "", ruby_annotation=ruby_annotation)
    return _clean_markup(expanded, inline=True)


def split_sections(text: str) -> list[dict[str, Any]]:
    """Split rendered text into sections using ``##`` heading markers."""
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] = {"level": 0, "title": "", "lines": []}
    for line in (text or "").splitlines():
        match = SECTION_LINE_RE.match(line)
        if match:
            sections.append(current)
            current = {
                "level": len(match.group(1)),
                "title": match.group(2).strip(),
                "lines": [],
            }
        else:
            current["lines"].append(line)
    sections.append(current)

    result: list[dict[str, Any]] = []
    for section in sections:
        content = "\n".join(section["lines"]).strip()
        if section["title"] or content:
            result.append(
                {
                    "level": section["level"],
                    "title": section["title"],
                    "content": content,
                }
            )
    return result


def section_titles(text: str) -> list[str]:
    """Return the non-empty section headings of a rendered page."""
    return [section["title"] for section in split_sections(text) if section["title"]]


SECTION_ALIASES = {
    "staff": ("staff的话", "staff的話", "staff附言", "staff", "制作人员", "制作"),
    "制作": ("staff的话", "staff的話", "staff附言", "staff", "制作人员", "制作"),
    "歌词": ("歌词", "歌詞"),
    "歌詞": ("歌词", "歌詞"),
    "曲目": ("收录曲目", "曲目", "曲目列表", "tracklist", "曲目表"),
    "收录曲目": ("收录曲目", "曲目", "曲目列表", "曲目表"),
    "简介": ("简介", "介绍", "概述", "概要"),
    "介绍": ("简介", "介绍", "概述", "概要"),
    "历史": ("历史", "发展", "经历"),
    "二次创作": ("二次创作", "二次創作", "翻唱", "衍生作品"),
    "杂谈": ("杂谈", "雜談", "轶事", "花絮"),
    "注释": ("注释及外部链接", "注释与外部链接", "注释", "外部链接"),
    "外部链接": ("注释及外部链接", "注释与外部链接", "外部链接"),
}


def _normalize_section_name(name: str) -> str:
    return re.sub(r"\s+", "", (name or "")).casefold()


def _section_score(title: str, target: str) -> int:
    normalized_title = _normalize_section_name(title)
    normalized_target = _normalize_section_name(target)
    if not normalized_title or not normalized_target:
        return 0
    if normalized_title == normalized_target:
        return 100
    if normalized_target in normalized_title or normalized_title in normalized_target:
        return 70

    aliases = SECTION_ALIASES.get(normalized_target, ())
    for alias in aliases:
        normalized_alias = _normalize_section_name(alias)
        if normalized_alias == normalized_title:
            return 90
        if normalized_alias in normalized_title or normalized_title in normalized_alias:
            return 60
    return 0


def find_section(text: str, name: str) -> dict[str, Any] | None:
    """Find a section and return its title, level and body (incl. subsections)."""
    if not name:
        return None

    lines = (text or "").splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = SECTION_LINE_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))

    scored: list[tuple[int, int, int, str]] = []
    for index, level, title in headings:
        score = _section_score(title, name)
        if score:
            scored.append((score, index, level, title))

    if not scored:
        return None

    score, start_index, level, title = max(scored, key=lambda item: (item[0], -item[1]))
    end_index = len(lines)
    for index, next_level, _ in headings:
        if index > start_index and next_level <= level:
            end_index = index
            break

    content = "\n".join(lines[start_index + 1 : end_index]).strip()
    return {
        "title": title,
        "level": level,
        "content": content,
        "score": score,
    }


def intro_text(text: str) -> str:
    """Return the lead section of a rendered page."""
    sections = split_sections(text)
    if not sections:
        return ""
    if not sections[0]["title"]:
        return sections[0]["content"]
    return sections[0]["content"]


def extract_infobox(wikitext: str) -> dict[str, Any]:
    """Parse the first known infobox and every song version it contains."""
    result: dict[str, Any] = {
        "type": "page",
        "template": "",
        "fields": {},
        "versions": [],
        "links": [],
    }

    for names, page_type in INFOBOX_SPECS:
        templates = find_named_templates(wikitext or "", names)
        if not templates:
            continue

        result["type"] = page_type
        result["template"] = templates[0].name.strip()
        versions: list[dict[str, Any]] = []
        all_links: list[dict[str, str]] = []
        for template in templates:
            fields: dict[str, str] = {}
            links: list[dict[str, str]] = []

            for raw_key, raw_value in template.params.items():
                key = raw_key.strip()
                if not key or key.casefold() in SKIP_FIELD_KEYS:
                    continue
                value = render_inline(raw_value)
                if not value:
                    continue

                if key.casefold() == "bb_id":
                    for video_id in re.findall(r"(?:av\d+|BV[0-9A-Za-z]+)", raw_value):
                        links.append(
                            {
                                "label": f"bilibili {video_id}",
                                "url": f"https://www.bilibili.com/video/{video_id}",
                            }
                        )
                elif key.casefold() == "wyy_id":
                    for song_id in re.findall(r"\d{3,}", raw_value):
                        links.append(
                            {
                                "label": f"网易云音乐 {song_id}",
                                "url": f"https://music.163.com/song?id={song_id}",
                            }
                        )
                elif key.casefold() == "yt_id":
                    for video_id in re.findall(r"[0-9A-Za-z_-]{6,}", raw_value):
                        links.append(
                            {
                                "label": f"YouTube {video_id}",
                                "url": f"https://www.youtube.com/watch?v={video_id}",
                            }
                        )

                for match in re.finditer(
                    r"\[(https?://[^\s\]]+)\s+([^\]]+)\]", raw_value
                ):
                    links.append(
                        {
                            "label": render_inline(
                                match.group(2), ruby_annotation=False
                            ),
                            "url": match.group(1),
                        }
                    )

                fields[key] = value

            if fields:
                versions.append({"fields": fields, "links": links})
                all_links.extend(links)

        if versions:
            result["versions"] = versions
            result["fields"] = versions[0]["fields"]
            result["links"] = _dedupe_links(all_links)
        return result

    if _is_disambiguation(wikitext):
        result["type"] = "disambiguation"
    return result


def _dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        url = link.get("url", "").strip()
        label = link.get("label", "").strip()
        if not url:
            continue
        key = (label, url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"label": label or url, "url": url})
    return deduped


def extract_tracks(wikitext: str) -> list[dict[str, Any]]:
    """Parse album ``Tracklist`` templates into structured track rows."""
    tracks: list[dict[str, Any]] = []
    for template in find_named_templates(wikitext or "", ("tracklist",)):
        rows, extra_label = _tracklist_rows(template)
        for row in rows:
            track: dict[str, Any] = {
                "index": row["index"],
                "title": render_inline(row["title"]),
            }
            for field, label in TRACK_FIELD_LABELS:
                value = row.get(field)
                if not value:
                    continue
                if field == "extra":
                    track["extra"] = render_inline(value)
                    track["extra_label"] = extra_label
                else:
                    track[field] = render_inline(value)
            if track["title"]:
                tracks.append(track)
    return tracks


def extract_staff(wikitext: str) -> list[dict[str, str]]:
    """Parse ``VOCALOID Songbox Introduction`` staff tables into role/name pairs."""
    templates = find_named_templates(
        wikitext or "",
        ("vocaloid songbox introduction", "songbox introduction"),
    )
    staff: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for template in templates:
        groups: dict[int, str] = {}
        names: dict[int, str] = {}
        for raw_key, raw_value in template.params.items():
            key = raw_key.strip()
            group_match = re.fullmatch(r"group(\d+)", key, re.IGNORECASE)
            list_match = re.fullmatch(r"list(\d+)", key, re.IGNORECASE)
            if group_match:
                groups[int(group_match.group(1))] = raw_value
            elif list_match:
                names[int(list_match.group(1))] = raw_value

        for number in sorted(set(groups) | set(names)):
            role = render_inline(groups.get(number, ""), ruby_annotation=False)
            name = render_inline(names.get(number, ""), ruby_annotation=False)
            role = re.sub(r"\s*/\s*", "/", role).strip(" ：:")
            name = name.strip(" ：:")
            if not role or not name:
                continue
            key = (role, name)
            if key in seen:
                continue
            seen.add(key)
            staff.append({"role": role, "name": name})

    return staff


def extract_achievements(wikitext: str) -> list[str]:
    """Extract achievement banners such as 神话曲 / 传说曲 / 殿堂曲."""
    achievements: list[str] = []
    pattern = re.compile(
        r"\{\{\s*([^{}|]*?(?:题头|神话曲|传说曲|殿堂曲)[^{}|]*?)\s*(?=\||\}\})",
        re.IGNORECASE,
    )
    for match in pattern.finditer(wikitext or ""):
        name = match.group(1).strip()
        name = re.sub(r"^template\s*:\s*", "", name, flags=re.IGNORECASE)
        name = re.sub(r"题头$", "", name).strip()
        if name and name not in achievements:
            achievements.append(name)
    return achievements


def _is_disambiguation(wikitext: str) -> bool:
    text = wikitext or ""
    if re.search(
        r"\{\{\s*(?:disambig|消歧义|消歧义页)\s*(?:\||\}\})", text, re.IGNORECASE
    ):
        return True
    return bool(re.search(r"(?:可以是指|可以指|可能是指)[:：]", text))


def detect_page_type(wikitext: str) -> str:
    """Return song/producer/voicebank/album/disambiguation/page for a page."""
    return extract_infobox(wikitext).get("type", "page")


def extract_lyrics(text: str) -> str:
    """Return the body of the 歌词 section from rendered page text."""
    section = find_section(text, "歌词")
    if not section or not section.get("content"):
        return ""
    return section["content"].strip()
