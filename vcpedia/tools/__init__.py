"""Query tools exposed by the VCPedia plugin."""

from .full_page import get_full_page
from .info import get_page_info
from .lyrics import get_lyrics
from .search_page import search_wiki_page
from .section import get_page_section
from .summary import get_wiki_summary

__all__ = [
    "search_wiki_page",
    "get_wiki_summary",
    "get_page_info",
    "get_lyrics",
    "get_page_section",
    "get_full_page",
]
