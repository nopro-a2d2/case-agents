"""Phase 7: entity/concept 페이지 임베딩 인덱스 빌드.

산출물 (`<case>/cache/embeddings/`):

- ``vectors.npy`` — ``(N, EMBEDDING_DIM)`` float32, L2 정규화 완료
- ``index.json`` — ``[{file, id, name_ko, type}]``, vectors 행 인덱스와 동일 순서
- ``manifest.json`` — ``{model, dim, files: {<file>: sha1}}``. 다음 빌드에서
  변경된 페이지만 재임베딩하기 위한 idempotency 키. 모델/차원 변경도 hash 에
  반영돼 자동 전체 재빌드.

Phase 4 (cross_ref) 가 페이지 본문을 수정하므로 Phase 4 **이후** 에 실행해야 한다.
"""

import asyncio
import json
import logging
from pathlib import Path

import frontmatter
import numpy as np

from wiki_builder.config import wiki_settings
from wiki_builder.embedding_store import (
    build_doc_text,
    compute_content_hash,
    embed_texts,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100
_CONCURRENCY = 10
# sources 포함: source-only 사실(예: 단일 수사보고서 메모)이 entity/concept으로
# 합성되지 않더라도 의미 검색으로 도달 가능하게 한다.
_SUBDIRS = ("entities", "concepts", "sources")
# source 페이지는 detailed_content 누적으로 길어질 수 있어 entity/concept 보다 큰 본문을 임베딩한다.
_SOURCE_MAX_BODY_CHARS = 6000


def _scan_pages() -> list[dict]:
    """entity/concept 페이지를 모두 스캔해서 임베딩 입력 후보 리스트 반환.

    각 항목: ``{file, id, name_ko, type, doc_text, hash}``
    """
    wiki_dir: Path = wiki_settings.WIKI_OUTPUT_DIR
    if wiki_dir is None:
        raise RuntimeError("WIKI_OUTPUT_DIR 미설정 — apply_case_path() 호출 누락")

    model = wiki_settings.EMBEDDING_MODEL
    dim = wiki_settings.EMBEDDING_DIM
    pages: list[dict] = []

    for subdir in _SUBDIRS:
        d = wiki_dir / subdir
        if not d.exists():
            continue
        for path in sorted(d.glob("*.md")):
            post = frontmatter.load(str(path))
            meta = dict(post.metadata)
            entry_type = meta.get("type", subdir.rstrip("s"))
            # source 페이지는 name_ko 가 없고 title 만 있으므로 fallback 적용.
            name_ko = meta.get("name_ko") or meta.get("title") or path.stem
            aliases = list(meta.get("aliases") or [])
            max_chars = _SOURCE_MAX_BODY_CHARS if entry_type == "source" else 2000
            doc_text = build_doc_text(name_ko, aliases, post.content, max_body_chars=max_chars)
            file_rel = f"{subdir}/{path.name}"
            pages.append(
                {
                    "file": file_rel,
                    "id": path.stem,
                    "name_ko": name_ko,
                    "type": entry_type,
                    "doc_text": doc_text,
                    "hash": compute_content_hash(doc_text, model, dim),
                }
            )
    return pages


def _load_existing(emb_dir: Path) -> tuple[dict | None, np.ndarray | None]:
    """기존 manifest + vectors 로드 (있으면). 없거나 정합성 깨지면 (None, None)."""
    man_path = emb_dir / "manifest.json"
    vec_path = emb_dir / "vectors.npy"
    idx_path = emb_dir / "index.json"
    if not (man_path.exists() and vec_path.exists() and idx_path.exists()):
        return None, None
    try:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
        vectors = np.load(vec_path)
        old_index = json.loads(idx_path.read_text(encoding="utf-8"))
        if vectors.shape[0] != len(old_index):
            logger.warning("기존 인덱스 정합성 깨짐 → 전체 재빌드")
            return None, None
        # 모델/차원 변경 시 전체 재빌드
        if (
            manifest.get("model") != wiki_settings.EMBEDDING_MODEL
            or manifest.get("dim") != wiki_settings.EMBEDDING_DIM
        ):
            logger.info(
                "model/dim 변경 (%s/%s → %s/%s) → 전체 재빌드",
                manifest.get("model"),
                manifest.get("dim"),
                wiki_settings.EMBEDDING_MODEL,
                wiki_settings.EMBEDDING_DIM,
            )
            return None, None
        # file → row index, file → vector 매핑을 위해 manifest 에 별도 보관
        # (manifest 의 files 는 hash 만 저장; row 매핑은 old_index 의 순서 사용)
        manifest["_old_file_to_row"] = {e["file"]: i for i, e in enumerate(old_index)}
        return manifest, vectors
    except (ValueError, OSError, json.JSONDecodeError) as e:
        logger.warning("기존 인덱스 로드 실패 (%s) → 전체 재빌드", e)
        return None, None


async def _embed_batches(texts: list[str], concurrency: int = _CONCURRENCY) -> np.ndarray:
    """배치 단위로 임베딩 (Semaphore 로 동시성 제한)."""
    if not texts:
        return np.zeros((0, wiki_settings.EMBEDDING_DIM), dtype=np.float32)

    sem = asyncio.Semaphore(concurrency)
    batches = [texts[i : i + _BATCH_SIZE] for i in range(0, len(texts), _BATCH_SIZE)]

    async def run_batch(idx: int, batch: list[str]) -> tuple[int, np.ndarray]:
        async with sem:
            arr = await asyncio.to_thread(embed_texts, batch)
            logger.info(
                "Phase 7: 배치 %d/%d 완료 (%d개)", idx + 1, len(batches), len(batch)
            )
            return idx, arr

    results = await asyncio.gather(
        *[run_batch(i, b) for i, b in enumerate(batches)]
    )
    results.sort(key=lambda r: r[0])
    return np.concatenate([r[1] for r in results], axis=0)


async def run_phase7(concurrency: int = _CONCURRENCY) -> dict[str, int]:
    """Phase 7 entry point.

    Returns: ``{"total": N, "new": k, "updated": m, "unchanged": u}``
    """
    if wiki_settings.CACHE_DIR is None or wiki_settings.WIKI_OUTPUT_DIR is None:
        raise RuntimeError("CACHE_DIR/WIKI_OUTPUT_DIR 미설정")

    emb_dir = wiki_settings.CACHE_DIR / "embeddings"
    emb_dir.mkdir(parents=True, exist_ok=True)

    pages = _scan_pages()
    if not pages:
        logger.warning("Phase 7: entity/concept 페이지가 없음 — 인덱스 빌드 skip")
        return {"total": 0, "new": 0, "updated": 0, "unchanged": 0}

    old_manifest, old_vectors = _load_existing(emb_dir)
    old_files: dict[str, str] = {}
    old_file_to_row: dict[str, int] = {}
    if old_manifest is not None:
        old_files = old_manifest.get("files", {})
        old_file_to_row = old_manifest.pop("_old_file_to_row", {})

    # 변경분 식별
    to_embed: list[dict] = []
    reuse: list[dict] = []
    for p in pages:
        if old_files.get(p["file"]) == p["hash"] and p["file"] in old_file_to_row:
            reuse.append(p)
        else:
            to_embed.append(p)

    new_count = sum(1 for p in to_embed if p["file"] not in old_files)
    updated_count = len(to_embed) - new_count

    logger.info(
        "Phase 7: 총 %d개 (재사용 %d, 신규 %d, 갱신 %d)",
        len(pages),
        len(reuse),
        new_count,
        updated_count,
    )

    # 새 임베딩
    new_vectors = await _embed_batches([p["doc_text"] for p in to_embed], concurrency)

    # 최종 vectors / index 합성 (pages 순서를 보존)
    embed_lookup: dict[str, np.ndarray] = {
        p["file"]: new_vectors[i] for i, p in enumerate(to_embed)
    }
    final_index: list[dict] = []
    final_rows: list[np.ndarray] = []
    for p in pages:
        if p["file"] in embed_lookup:
            vec = embed_lookup[p["file"]]
        else:
            row = old_file_to_row[p["file"]]
            vec = old_vectors[row]
        final_index.append(
            {
                "file": p["file"],
                "id": p["id"],
                "name_ko": p["name_ko"],
                "type": p["type"],
            }
        )
        final_rows.append(vec)

    final_vectors = np.stack(final_rows, axis=0).astype(np.float32)

    # 저장
    np.save(emb_dir / "vectors.npy", final_vectors)
    (emb_dir / "index.json").write_text(
        json.dumps(final_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    new_manifest = {
        "model": wiki_settings.EMBEDDING_MODEL,
        "dim": wiki_settings.EMBEDDING_DIM,
        "files": {p["file"]: p["hash"] for p in pages},
    }
    (emb_dir / "manifest.json").write_text(
        json.dumps(new_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(
        "Phase 7 완료: vectors %s, index %d개 → %s",
        final_vectors.shape,
        len(final_index),
        emb_dir,
    )
    return {
        "total": len(pages),
        "new": new_count,
        "updated": updated_count,
        "unchanged": len(reuse),
    }
