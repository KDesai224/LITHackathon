"""Rasterisation helpers that turn a PyMuPDF page into a numpy image."""

from __future__ import annotations

import numpy as np
import pymupdf


def page_to_array(page: pymupdf.Page, dpi: int = 300) -> np.ndarray:
    """Render a PDF page to an RGB ``uint8`` numpy array.

    Args:
        page: PyMuPDF page.
        dpi: Rendering resolution (300 matches typical office scans).

    Returns:
        Array of shape ``(height, width, 3)``.
    """
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    array = np.frombuffer(pix.samples, dtype=np.uint8)
    return array.reshape(pix.height, pix.width, pix.n)
