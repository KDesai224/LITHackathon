"""Integration tests for the local ``BAAI/bge-small-en-v1.5`` embedding model.

These tests hit the network on the very first run (the model downloads to
``~/.cache/huggingface/hub``) and are then served from the local cache. Run the
whole suite normally; if you are fully offline, deselect this module with
``uv run pytest -k "not embeddings"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

#: Fixed output dimension of BAAI/bge-small-en-v1.5.
EMBEDDING_MODEL_DIMENSION = 384

SAMPLE_TEXT = "Jane Ong owes John Doe $10,000 for a sofa sold on 2 September 2026."


def test_bge_embedding_dimension(embedding_model: SentenceTransformer) -> None:
    vector = embedding_model.encode(SAMPLE_TEXT, normalize_embeddings=True)
    assert len(vector) == EMBEDDING_MODEL_DIMENSION
    assert np.asarray(vector).shape == (EMBEDDING_MODEL_DIMENSION,)


def test_bge_embeddings_are_deterministic(
    embedding_model: SentenceTransformer,
) -> None:
    first = embedding_model.encode(SAMPLE_TEXT, normalize_embeddings=True)
    second = embedding_model.encode(SAMPLE_TEXT, normalize_embeddings=True)
    assert np.allclose(first, second, atol=1e-6)


def test_bge_semantic_similarity_ranks_related_above_unrelated(
    embedding_model: SentenceTransformer,
) -> None:
    related = "breach of contract for unpaid goods"
    unrelated = "baking sourdough bread with rosemary"
    vectors = embedding_model.encode(
        [SAMPLE_TEXT, related, unrelated], normalize_embeddings=True
    )
    claim, related_vec, unrelated_vec = vectors
    assert float(np.dot(claim, related_vec)) > float(np.dot(claim, unrelated_vec))


def test_bge_accepts_batch_inputs(embedding_model: SentenceTransformer) -> None:
    vectors = embedding_model.encode(
        [SAMPLE_TEXT, "a second unrelated claim narrative"],
        normalize_embeddings=True,
    )
    assert len(vectors) == 2
    assert all(len(vector) == EMBEDDING_MODEL_DIMENSION for vector in vectors)


def test_package_local_embedder_adapter_dimension() -> None:
    """The sct_intake adapter produces 384-dim vectors through the real model."""
    from sct_intake.embedders import SentenceTransformerEmbeddingModel

    model = SentenceTransformerEmbeddingModel()
    vectors = model.embed([SAMPLE_TEXT])
    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_MODEL_DIMENSION
