"""Vertex AI 백엔드 GenAI 클라이언트 팩토리.

google-genai SDK는 단일 인터페이스로 Gemini Developer API와 Vertex AI를
모두 지원한다. 본 프로젝트는 Vertex AI를 사용하므로 `vertexai=True`로
클라이언트를 생성한다.

인증: GOOGLE_APPLICATION_CREDENTIALS 환경변수가 가리키는 서비스 계정 JSON.
프로젝트/위치: wiki_settings.GCP_PROJECT, wiki_settings.VERTEX_LOCATION.
"""

from google import genai
from google.genai import types

from wiki_builder.config import wiki_settings

_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    """프로세스 싱글톤 GenAI(Vertex) 클라이언트 반환.

    ADC 토큰 캐시와 HTTP 커넥션 풀을 공유하기 위해 모듈 전역으로 1개만 둔다.
    재시도 정책은 Vertex AI 권장값(SDK 기본과 동일)을 명시화하여, 향후 SDK
    디폴트가 바뀌더라도 동작이 고정되도록 한다.
    """
    global _client
    if _client is None:
        if not wiki_settings.GCP_PROJECT or not wiki_settings.VERTEX_LOCATION:
            raise RuntimeError(
                "Vertex AI 사용을 위해 GCP_PROJECT, VERTEX_LOCATION "
                "환경변수를 설정하세요. (.env 또는 셸 환경)"
            )
        _client = genai.Client(
            vertexai=True,
            project=wiki_settings.GCP_PROJECT,
            location=wiki_settings.VERTEX_LOCATION,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    initial_delay=1.0,
                    max_delay=60.0,
                    exp_base=2.0,
                    jitter=1.0,
                    attempts=5,
                    http_status_codes=[408, 429, 500, 502, 503, 504],
                ),
                timeout=120 * 1000,  # 120s — Tier C 긴 컨텍스트 문서 대응
            ),
        )
    return _client
