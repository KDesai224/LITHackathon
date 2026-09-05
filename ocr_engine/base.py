"""Abstract OCR engine interface for page-image text recognition.

Engines are deliberately small: they take one rasterised page image (an RGB
``numpy.ndarray``) and return the recognised text. Document handling (PDF
text layers, rasterisation, ordering) lives in :mod:`ocr_engine.service`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class OCREngine(ABC):
    """Recognise text from a single page image."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine identifier."""

    @abstractmethod
    def recognize(self, image: np.ndarray) -> str:
        """Return the recognised text for one page image.

        Args:
            image: RGB ``uint8`` array of shape ``(height, width, 3)``.

        Returns:
            The page text, with line breaks between recognised lines. An empty
            string means no text was detected.
        """

    def close(self) -> None:
        """Release any engine-owned resources (no-op by default)."""
