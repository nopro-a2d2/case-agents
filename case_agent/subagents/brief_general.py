"""범용 서면 작성 writer subagent.

민사 준비서면(``brief_civil``) 이외의 모든 서면을 단일 writer 로 처리한다.
종류별 헤딩 키워드 강제는 없고 (verify._REQUIRED_HEADINGS["general_brief"] = ()),
기본 작성 가이드(섹션 단위 호출 / ``@@[id]`` 인용 / ``## <id>. <title>`` 헤딩 부착
금지)만 따른다. 종류별 구조·문체 가이드는 planner 가 outline + context 로 전달한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..briefs import BRIEF_KINDS
from ._brief_base import build_brief_subagent_dict

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..tools.search import Embedder
    from ..workspace import Workspace


_EXTRA = """\
# 범용 서면 — Writer 지시

## 종류별 가이드 출처
- 서면 종류·우리 측 입장·목적·핵심 쟁점·문체 규칙은 모두 context_markdown 에 있다.
- 동의/부동의 표시·인부 표시·원심 인용·청구취지 같은 종류 고유 표현은 context 가
  지정한 경우에만 사용. context 에 명시되지 않은 형식을 임의로 도입하지 않는다.

## Self-review (반환 직전)
- context 가 명시한 섹션 의도·인용 자료가 본문에 반영되었는가
- 인용 괄호는 문장 종결 위치(``… 입니다 (@@[3]).``) 에 있는가
"""


def build_subagent(
    workspace: "Workspace",
    embedder: "Embedder",
    *,
    model: "BaseChatModel | None" = None,
) -> dict[str, Any]:
    return build_brief_subagent_dict(
        BRIEF_KINDS["general_brief"],
        workspace,
        embedder,
        model=model,
        extra_prompt=_EXTRA,
    )
