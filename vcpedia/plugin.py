"""Compatibility shim.

The real AstrBot Star class is defined in main.py.
"""

try:
    from ..main import VCPediaPlugin
except ImportError:
    from main import VCPediaPlugin

__all__ = ["VCPediaPlugin"]
