"""Phase 1: 소스 페이지 컴파일"""

import json
import logging
from pathlib import Path

from wiki_builder.config import wiki_settings
from wiki_builder.models import CompileResult, CompileResultLLM, Document
from wiki_builder.prompts import SOURCE_COMPILE_PROMPT, SOURCE_COMPILE_SYSTEM

logger = logging.getLogger(__name__)


def build_batch_request(doc: Document) -> dict:
    """문서 1개를 Batch API 요청으로 변환"""
    prompt = SOURCE_COMPILE_PROMPT.format(
        doc_id=doc.id,
        name=doc.name,
        category=doc.category,
        person=doc.person or "없음",
        total_page=doc.total_page,
        token_count=doc.token_count,
        full_text=doc.full_text,
    )
    return {
        "key": doc.id,
        "request": {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "system_instruction": {"parts": [{"text": SOURCE_COMPILE_SYSTEM}]},
            "generation_config": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
                "response_schema": CompileResultLLM.model_json_schema(),
            },
        },
    }


def _extract_first_json(raw_text: str) -> dict | None:
    """원문에서 첫 번째 유효 JSON 객체를 추출 (Extra data 대응)"""
    # 1차: 그대로 파싱
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return None
    except json.JSONDecodeError:
        pass

    # 2차: 중괄호 매칭으로 첫 번째 JSON 객체 추출
    depth = 0
    start = raw_text.find("{")
    if start == -1:
        return None
    for i in range(start, len(raw_text)):
        if raw_text[i] == "{":
            depth += 1
        elif raw_text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw_text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_compile_result(doc_id: str, raw_text: str) -> CompileResult | None:
    """Batch API 응답을 CompileResult로 파싱"""
    data = _extract_first_json(raw_text)
    if data is None:
        logger.warning("컴파일 결과 파싱 실패: doc_id=%s", doc_id)
        return None
    try:
        return CompileResult(doc_id=doc_id, **data)
    except (ValueError, TypeError) as e:
        logger.warning("CompileResult 생성 실패: doc_id=%s, %s", doc_id, e)
        return None


def save_compile_cache(cache_dir: Path, doc_id: str, raw_text: str) -> None:
    """컴파일 결과를 캐시에 저장"""
    cache_path = cache_dir / "phase1_results" / f"{doc_id}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(raw_text, encoding="utf-8")


def load_compile_cache(cache_dir: Path, doc_id: str) -> str | None:
    """캐시에서 컴파일 결과 로드"""
    cache_path = cache_dir / "phase1_results" / f"{doc_id}.json"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    return None


def delete_compile_cache(cache_dir: Path, doc_id: str) -> None:
    """파싱 불가능한 캐시 파일을 제거하여 다음 빌드에서 자동 재호출되도록 한다."""
    cache_path = cache_dir / "phase1_results" / f"{doc_id}.json"
    cache_path.unlink(missing_ok=True)


def get_cached_doc_ids(cache_dir: Path) -> set[str]:
    """캐시된 문서 ID 목록"""
    results_dir = cache_dir / "phase1_results"
    if not results_dir.exists():
        return set()
    return {p.stem for p in results_dir.glob("*.json")}
