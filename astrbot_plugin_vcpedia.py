"""Compatibility shim.

Canonical plugin entry is main.py.
"""

try:
    from .main import VCPediaPlugin
except ImportError:
    from main import VCPediaPlugin

__all__ = ["VCPediaPlugin"]
