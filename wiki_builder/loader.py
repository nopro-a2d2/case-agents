"""Spark JSON 문서 로더"""

import asyncio
import json
import logging
from pathlib import Path

from wiki_builder.models import Document

logger = logging.getLogger(__name__)

CATEGORY_ORDER = [
    # 형사
    "공소장",
    # 민사 핵심 변론
    "소장",
    "답변서",
    "청구취지변경",
    "준비서면",
    "변론조서",
    "석명준비명령",
    # 조사/감정
    "수사보고서",
    "사실조회",
    "감정서",
    "진술",
    # 증거/참조
    "서증",
    "참조법문서",
    # 절차 부속
    "기일신청",
    "주소보정",
    "소송위임장",
    # 미분류
    "기타",
]


def infer_category_from_filename(stem: str) -> str:
    """파일명 stem 으로 민사/형사 카테고리 추론. 매칭 실패 시 '기타'."""
    s = stem
    if "공소장" in s:
        return "공소장"
    if "소장" in s:
        return "소장"
    if "답변서" in s and "석명" not in s:
        return "답변서"
    if "청구취지" in s:
        return "청구취지변경"
    if "준비서면" in s and "석명" not in s:
        return "준비서면"
    if "변론조서" in s:
        return "변론조서"
    if "석명준비명령" in s:
        return "석명준비명령"
    if "사실조회" in s:
        return "사실조회"
    if "감정서" in s or "감정신청" in s:
        return "감정서"
    if "수사보고" in s:
        return "수사보고서"
    if "진술" in s:
        return "진술"
    if "호증" in s or s.startswith(("원고_갑", "피고_을")):
        return "서증"
    if "기일" in s and "신청" in s:
        return "기일신청"
    if "주소보정" in s:
        return "주소보정"
    if "소송위임장" in s:
        return "소송위임장"
    return "기타"


async def load_document(path: Path) -> Document | None:
    """단일 JSON 파일을 Document로 로드"""
    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, path.read_text, "utf-8")
        data = json.loads(raw)
        if not data.get("category"):
            data["category"] = infer_category_from_filename(path.stem)
        return Document(**data)
    except Exception:
        logger.warning("문서 로드 실패: %s", path, exc_info=True)
        return None


async def load_all_documents(json_dir: Path) -> list[Document]:
    """모든 JSON 파일을 비동기 병렬 로드"""
    paths = sorted(json_dir.glob("*.json"))
    logger.info("JSON 파일 발견: %d개 (%s)", len(paths), json_dir)

    tasks = [load_document(p) for p in paths]
    results = await asyncio.gather(*tasks)
    docs = [d for d in results if d is not None]

    logger.info("문서 로드 완료: %d개 (실패 %d개)", len(docs), len(paths) - len(docs))
    return docs


def sort_by_category(docs: list[Document]) -> list[Document]:
    """카테고리 중요도순 정렬: 공소장 → 수사보고서 → 진술 → 참조법문서 → 기타"""

    def category_key(doc: Document) -> tuple[int, str]:
        try:
            idx = CATEGORY_ORDER.index(doc.category)
        except ValueError:
            idx = len(CATEGORY_ORDER)
        return (idx, doc.id)

    return sorted(docs, key=category_key)
