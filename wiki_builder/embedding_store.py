"""임베딩 인덱스 로드 및 의미 검색 (Hybrid Tier 2).

빌드 산출물 (vectors.npy + index.json + manifest.json) 은 wiki_builder/embedder.py 가
작성하고 이 모듈은 read-only 로 그것을 사용한다. chatbot 과 wiki_builder 양쪽이 import.

gemini-embedding-2 는 ``task_type`` 파라미터를 지원하지 않으므로, contents 텍스트
자체를 공식 권장 포맷으로 만들어 보낸다:

- 문서 (빌드): ``"title: {title} | text: {content}"`` (title 없으면 ``title: none``)
- 쿼리 (조회): ``"task: search result | query: {content}"``
"""

import hashlib
import json
import logging
from pathlib import Path

import numpy as np
from google.genai import types

from wiki_builder.config import wiki_settings
from wiki_builder.llm import get_genai_client

logger = logging.getLogger(__name__)

# 공식 문서 권장 포맷 — 빌드/조회가 동일 포맷이어야 retrieval 임베딩 공간에서 정합.
DOC_TEMPLATE = "title: {title} | text: {content}"
QUERY_TEMPLATE = "task: search result | query: {content}"


def _title_with_aliases(name_ko: str, aliases: list[str]) -> str:
    """name_ko 에 aliases 가 있으면 괄호로 풍부화. 식별 신호 강화."""
    if not aliases:
        return name_ko
    return f"{name_ko} ({', '.join(aliases)})"


def build_doc_text(
    name_ko: str, aliases: list[str], body: str, max_body_chars: int = 2000
) -> str:
    """빌드 시 임베딩 입력 텍스트 합성. 공식 Document Structure 적용.

    예: ``"title: 윤경림 | text: 전 KT 사장으로서…"``
        ``"title: 시장 접근법 (Market Approach) | text: …"``
    """
    title = _title_with_aliases(name_ko, aliases) or "none"
    excerpt = body[:max_body_chars]
    return DOC_TEMPLATE.format(title=title, content=excerpt)


def build_query_text(question: str) -> str:
    """조회 시 임베딩 입력 텍스트 합성."""
    return QUERY_TEMPLATE.format(content=question)


def compute_content_hash(doc_text: str, model: str, dim: int) -> str:
    """임베딩에 실제로 들어가는 문자열 + model + dim 의 sha1.

    셋 중 하나만 바뀌어도 hash 가 바뀌어 재임베딩이 트리거된다.
    """
    h = hashlib.sha1()
    h.update(doc_text.encode("utf-8"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(dim).encode("utf-8"))
    return h.hexdigest()


def embed_texts(texts: list[str], dim: int | None = None) -> np.ndarray:
    """텍스트 리스트를 임베딩 → L2 정규화된 (N, dim) float32 매트릭스.

    gemini-embedding-2 는 멀티모달 모델이라 ``contents=[t1, t2, ...]`` 를
    **interleaved 단일 입력** 으로 해석해 한 개 벡터만 반환한다. 따라서
    텍스트별로 호출해야 한다 (batch 가 필요하면 호출자가 동시성 제어).

    genai SDK 호출은 이 함수 안에서만 발생 (빌드/조회 일관성 강제).
    """
    if not texts:
        return np.zeros((0, dim or wiki_settings.EMBEDDING_DIM), dtype=np.float32)

    client = get_genai_client()
    target_dim = dim or wiki_settings.EMBEDDING_DIM
    vectors: list[list[float]] = []
    for text in texts:
        response = client.models.embed_content(
            model=wiki_settings.EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=target_dim),
        )
        vectors.append(list(response.embeddings[0].values))

    arr = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.where(norms == 0, 1.0, norms)


class EmbeddingIndex:
    """`<case>/cache/embeddings/` 의 인덱스를 메모리에 로드하고 코사인 검색.

    파일이 없으면 ``is_loaded=False`` 로 빈 상태 — 호출자가 의미 검색 분기를
    skip 하도록 한다 (인덱스 미빌드 환경에서도 챗봇은 정상 기동).
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or wiki_settings.CACHE_DIR
        self._vectors: np.ndarray | None = None
        self._entries: list[dict] = []
        self._model: str | None = None
        self._dim: int | None = None
        self._load()

    def _load(self) -> None:
        if self.cache_dir is None:
            return
        emb_dir = self.cache_dir / "embeddings"
        vec_path = emb_dir / "vectors.npy"
        idx_path = emb_dir / "index.json"
        man_path = emb_dir / "manifest.json"
        if not (vec_path.exists() and idx_path.exists()):
            return
        try:
            self._vectors = np.load(vec_path)
            self._entries = json.loads(idx_path.read_text(encoding="utf-8"))
            if man_path.exists():
                manifest = json.loads(man_path.read_text(encoding="utf-8"))
                self._model = manifest.get("model")
                self._dim = manifest.get("dim")
            if len(self._entries) != self._vectors.shape[0]:
                logger.warning(
                    "EmbeddingIndex 정합성 깨짐: index %d, vectors %d → 비활성화",
                    len(self._entries),
                    self._vectors.shape[0],
                )
                self._vectors = None
                self._entries = []
        except (ValueError, OSError, json.JSONDecodeError) as e:
            logger.warning("EmbeddingIndex 로드 실패: %s → 비활성화", e)
            self._vectors = None
            self._entries = []

    @property
    def is_loaded(self) -> bool:
        return self._vectors is not None and len(self._entries) > 0

    def __len__(self) -> int:
        return len(self._entries)

    def search(
        self,
        query: str,
        top_k: int | None = None,
        min_sim: float | None = None,
    ) -> list[tuple[str, float]]:
        """질문에 대한 top-K 페이지 검색. ``[(file_path, similarity), ...]`` 반환.

        벡터가 빌드 시 L2 정규화돼 있고 쿼리 벡터도 정규화하므로 dot product 가
        곧 코사인 유사도. ``min_sim`` 미달은 결과에서 제외.
        """
        if not self.is_loaded:
            return []

        k = top_k if top_k is not None else wiki_settings.SEMANTIC_TOP_K
        thr = min_sim if min_sim is not None else wiki_settings.SEMANTIC_MIN_SIM

        target_dim = self._dim or wiki_settings.EMBEDDING_DIM
        q_text = build_query_text(query)
        q_vec = embed_texts([q_text], dim=target_dim)[0]  # (dim,) L2 정규화 완료

        sims = self._vectors @ q_vec  # (N,) cosine
        # top-K 인덱스 (내림차순)
        if k >= len(sims):
            order = np.argsort(-sims)
        else:
            # argpartition 으로 부분정렬 후 그 K 개만 정렬 → O(N) + O(K log K)
            top_idx = np.argpartition(-sims, k)[:k]
            order = top_idx[np.argsort(-sims[top_idx])]

        results: list[tuple[str, float]] = []
        for i in order:
            sim = float(sims[i])
            if sim < thr:
                break
            results.append((self._entries[i]["file"], sim))
        return results
