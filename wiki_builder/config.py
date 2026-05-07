"""LLM Wiki 설정.

사건 스코프 경로(JSON_DIR / WIKI_OUTPUT_DIR / CACHE_DIR)는 환경변수로 받지 않고,
엔트리포인트(build_wiki.py / run_chatbot.py)가 CLI ``--case <폴더경로>`` option 으로
받은 경로를 :func:`apply_case_path` 로 wiki_settings 에 주입한다.
"""

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class WikiSettings(BaseSettings):
    # Gemini (Vertex AI 백엔드)
    # GOOGLE_APPLICATION_CREDENTIALS 는 WikiSettings 필드가 아니라 google-auth 가 os.environ 에서 직접 읽음.
    # pydantic-settings 는 .env 를 인스턴스 속성에만 채울 뿐 os.environ 에 주입하지 않으므로,
    # 엔트리포인트(build_wiki.py / run_chatbot.py)에서 dotenv.load_dotenv() 를 먼저 호출해야 함.
    # case_agent 와 동일한 .env 키(GCP_PROJECT / VERTEX_LOCATION)를 우선 사용하고,
    # GOOGLE_CLOUD_* 도 fallback 으로 허용.
    GCP_PROJECT: str = Field(
        default="",
        validation_alias=AliasChoices("GCP_PROJECT", "GOOGLE_CLOUD_PROJECT"),
    )
    VERTEX_LOCATION: str = Field(
        default="",
        validation_alias=AliasChoices("VERTEX_LOCATION", "GOOGLE_CLOUD_LOCATION"),
    )
    BATCH_MODEL: str = "gemini-3.1-flash-lite-preview"
    REALTIME_MODEL: str = "gemini-3.1-flash-lite-preview"

    # Deprecated: 휴면 batch_client.py 전용. 활성 경로(realtime/QA)는 Vertex ADC 사용.
    GEMINI_API_KEY: str = ""

    # 사건 스코프 경로 — 엔트리포인트가 apply_case_path() 로 주입.
    # 직접 임포트해서 None 인 채로 사용하면 NoneType 오류로 명확히 실패하도록 None 유지.
    JSON_DIR: Path | None = None
    WIKI_OUTPUT_DIR: Path | None = None
    CACHE_DIR: Path | None = None

    # 전역 (사건 무관)
    LOG_DIR: Path = Path("./logs")

    # Batch API
    BATCH_POLL_INTERVAL: int = 30
    BATCH_TIMEOUT: int = 86400
    BATCH_FILE_THRESHOLD: int = 500

    # Pipeline
    TIER_A_MAX_TOKENS: int = 8000
    TIER_C_MIN_TOKENS: int = 30000
    QA_MAX_PAGES: int = 20

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8001

    # Embedding-based semantic search (Hybrid Tier 2)
    # gemini-embedding-2 는 task_type 미지원 — contents 텍스트에 공식 포맷 prefix 적용
    EMBEDDING_MODEL: str = "gemini-embedding-2"
    EMBEDDING_DIM: int = 768
    SEMANTIC_TOP_K: int = 8
    # gemini-embedding-2 의 retrieval 임베딩은 baseline 유사도가 ~0.55~0.65 범위라
    # 0.5 로는 인사말/무관 질의도 통과. 실측 (안녕하세요 0.645, 오늘 날씨 0.585,
    # 피고인이 누구인가요 0.747, 주요 쟁점 0.739) 기반 0.70 으로 설정.
    SEMANTIC_MIN_SIM: float = 0.70

    # Langfuse
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


wiki_settings = WikiSettings()


def apply_case_path(case_path: Path) -> None:
    """사건 폴더 경로를 wiki_settings 에 주입.

    엔트리포인트가 CLI ``--case`` option 으로 받은 경로를 가장 먼저 호출.
    파생 규칙:

    - ``JSON_DIR``        = ``<case>/json``
    - ``WIKI_OUTPUT_DIR`` = ``<case>/wiki-output``
    - ``CACHE_DIR``       = ``<case>/cache``

    :raises FileNotFoundError: 사건 폴더가 존재하지 않음
    :raises NotADirectoryError: 경로가 디렉터리가 아님
    """
    case = case_path.expanduser().resolve()
    if not case.exists():
        raise FileNotFoundError(f"사건 폴더가 존재하지 않음: {case}")
    if not case.is_dir():
        raise NotADirectoryError(f"사건 경로가 디렉터리가 아님: {case}")
    wiki_settings.JSON_DIR = case / "json"
    wiki_settings.WIKI_OUTPUT_DIR = case / "wiki-output"
    wiki_settings.CACHE_DIR = case / "cache"
