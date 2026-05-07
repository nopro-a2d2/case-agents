"""Vertex 2-tier model routing.

- Heavy (advanced reasoning, drafting, verification judgment) -> Claude Sonnet via Vertex.
- Light (summarisation, extraction, explore-agent body)         -> Gemini Flash via Vertex.
- Embedder (smart_search query encoding)                        -> Vertex AI text embeddings,
  defaulted to the same model that produced the on-disk index (`gemini-embedding-2`).

Auth is **always explicit**: credentials come from the service-account JSON key
pointed to by ``GOOGLE_APPLICATION_CREDENTIALS`` (see :mod:`case_agent.auth`).
There is no fallback to gcloud ADC. The fail-fast project/credential checks
keep test imports cheap — Vertex clients are only instantiated when a builder
is actually called.
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

from ..auth import get_credentials


DEFAULT_HEAVY_MODEL = os.environ.get("CASE_AGENT_HEAVY_MODEL", "claude-sonnet-4-6")
DEFAULT_LIGHT_MODEL = os.environ.get("CASE_AGENT_LIGHT_MODEL", "gemini-3-flash-preview")
DEFAULT_EMBEDDING_MODEL = os.environ.get("CASE_AGENT_EMBED_MODEL", "gemini-embedding-2")
# Must match the prebuilt index's manifest.json `dim`. gemini-embedding-2's
# native output is 3072; we project to 768 via output_dimensionality so query
# vectors line up with the on-disk (N, 768) vectors.npy.
DEFAULT_EMBEDDING_DIM = int(os.environ.get("CASE_AGENT_EMBED_DIM", "768"))
DEFAULT_LOCATION = os.environ.get("VERTEX_LOCATION", "us-east5")


def _project() -> str:
    p = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not p:
        raise RuntimeError(
            "GCP_PROJECT (or GOOGLE_CLOUD_PROJECT) env var must be set "
            "before constructing a Vertex model."
        )
    return p


def build_heavy(
    *,
    model: str | None = None,
    location: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 8192,
):
    """Claude Sonnet via Vertex (langchain ChatAnthropicVertex)."""
    from langchain_google_vertexai.model_garden import ChatAnthropicVertex

    return ChatAnthropicVertex(
        model_name=model or DEFAULT_HEAVY_MODEL,
        project=_project(),
        location=location or DEFAULT_LOCATION,
        credentials=get_credentials(),
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_light(
    *,
    model: str | None = None,
    location: str | None = None,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
):
    """Gemini Flash via Vertex."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model or DEFAULT_LIGHT_MODEL,
        project=_project(),
        location=location or DEFAULT_LOCATION,
        credentials=get_credentials(),
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


@lru_cache(maxsize=4)
def _embedding_client(model: str, location: str, output_dim: int):
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=model,
        credentials=get_credentials(),
        output_dimensionality=output_dim,
    )


class VertexEmbedderAdapter:
    """Thin adapter so smart_search.Embedder protocol stays decoupled from langchain."""

    def __init__(
        self,
        *,
        model: str | None = None,
        location: str | None = None,
        output_dim: int | None = None,
    ):
        self._model = model or DEFAULT_EMBEDDING_MODEL
        self._location = location or DEFAULT_LOCATION
        self._output_dim = output_dim if output_dim is not None else DEFAULT_EMBEDDING_DIM

    def embed(self, text: str) -> np.ndarray:
        client = _embedding_client(self._model, self._location, self._output_dim)
        vec = np.asarray(client.embed_query(text), dtype=np.float32)
        if vec.shape != (self._output_dim,):
            raise RuntimeError(
                f"embedder returned shape {vec.shape}, expected ({self._output_dim},); "
                f"model={self._model} location={self._location}"
            )
        return vec

    async def aembed(self, text: str) -> np.ndarray:
        client = _embedding_client(self._model, self._location, self._output_dim)
        vec = np.asarray(await client.aembed_query(text), dtype=np.float32)
        if vec.shape != (self._output_dim,):
            raise RuntimeError(
                f"embedder returned shape {vec.shape}, expected ({self._output_dim},); "
                f"model={self._model} location={self._location}"
            )
        return vec


def build_embedder(
    *,
    model: str | None = None,
    location: str | None = None,
    output_dim: int | None = None,
) -> VertexEmbedderAdapter:
    return VertexEmbedderAdapter(model=model, location=location, output_dim=output_dim)
