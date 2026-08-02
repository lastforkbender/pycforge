"""Headless PyCForge laboratory audits."""

from .keyword_audit import audit_keyword
from .keyword_only_audit import audit_keyword_only

__all__ = ["audit_keyword", "audit_keyword_only"]
