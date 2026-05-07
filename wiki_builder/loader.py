"""Spark JSON 문서 로더"""

import asyncio
import json
import logging
from pathlib import Path

from wiki_builder.models import SparkDocument

logger = logging.getLogger(__name__)

CATEGORY_ORDER = ["공소장", "수사보고서", "진술", "참조법문서", "기타"]


async def load_document(path: Path) -> SparkDocument | None:
    """단일 JSON 파일을 SparkDocument로 로드"""
    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, path.read_text, "utf-8")
        data = json.loads(raw)
        return SparkDocument(**data)
    except Exception:
        logger.warning("문서 로드 실패: %s", path, exc_info=True)
        return None


async def load_all_documents(json_dir: Path) -> list[SparkDocument]:
    """모든 JSON 파일을 비동기 병렬 로드"""
    paths = sorted(json_dir.glob("*.json"))
    logger.info("JSON 파일 발견: %d개 (%s)", len(paths), json_dir)

    tasks = [load_document(p) for p in paths]
    results = await asyncio.gather(*tasks)
    docs = [d for d in results if d is not None]

    logger.info("문서 로드 완료: %d개 (실패 %d개)", len(docs), len(paths) - len(docs))
    return docs


def sort_by_category(docs: list[SparkDocument]) -> list[SparkDocument]:
    """카테고리 중요도순 정렬: 공소장 → 수사보고서 → 진술 → 참조법문서 → 기타"""

    def category_key(doc: SparkDocument) -> tuple[int, str]:
        try:
            idx = CATEGORY_ORDER.index(doc.category)
        except ValueError:
            idx = len(CATEGORY_ORDER)
        return (idx, doc.id)

    return sorted(docs, key=category_key)
