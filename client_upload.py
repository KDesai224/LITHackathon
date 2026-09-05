"""Compatibility shim for the SCT intake domain/model.

All implementation moved to :mod:`sct_intake`. This module re-exports the same
objects so existing ``from client_upload import SCTCase`` imports keep working
unchanged after the package split.
"""

from __future__ import annotations

from sct_intake import (
    DEFAULT_UPLOAD_PATH,
    NATURE_OF_DISPUTE_CHOICES,
    FieldExtractor,
    NatureOfDispute,
    SCTCase,
)

__all__ = [
    "DEFAULT_UPLOAD_PATH",
    "NATURE_OF_DISPUTE_CHOICES",
    "FieldExtractor",
    "NatureOfDispute",
    "SCTCase",
]
