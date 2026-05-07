"""데이터 모델 정의"""

from datetime import datetime

from pydantic import BaseModel, Field


class PageContent(BaseModel):
    page: int
    text: str


class SparkDocument(BaseModel):
    id: str
    name: str
    summary: str
    total_page: int
    token_count: int
    category: str
    person: str | None = None
    content: list[PageContent]

    @property
    def full_text(self) -> str:
        return "\n\n".join(f"[페이지 {p.page}]\n{p.text}" for p in self.content)


class ExtractedEntity(BaseModel):
    name_ko: str
    type: str  # person, org, place, other


class ExtractedConcept(BaseModel):
    name_ko: str
    description: str


class DateFact(BaseModel):
    date: str
    event: str
    pages: list[int] = Field(default_factory=list)


class AmountFact(BaseModel):
    amount: str
    context: str
    pages: list[int] = Field(default_factory=list)


class PersonFact(BaseModel):
    name: str
    role: str
    pages: list[int] = Field(default_factory=list)


class OrgFact(BaseModel):
    name: str
    role: str
    pages: list[int] = Field(default_factory=list)


class KeyFacts(BaseModel):
    dates: list[DateFact] = Field(default_factory=list)
    amounts: list[AmountFact] = Field(default_factory=list)
    persons: list[PersonFact] = Field(default_factory=list)
    organizations: list[OrgFact] = Field(default_factory=list)
    legal_provisions: list[str] = Field(default_factory=list)


class DetailedSentence(BaseModel):
    """detailed_content의 한 사실 단위. 페이지 출처는 pages 필드에만, text에는 인용 토큰 금지."""

    text: str
    pages: list[int] = Field(default_factory=list)


class CompileResult(BaseModel):
    """Phase 1 소스 컴파일 결과"""

    schema_version: int = 2
    doc_id: str
    summary: str
    key_facts: KeyFacts
    detailed_content: list[DetailedSentence]
    entities: list[ExtractedEntity]
    concepts: list[ExtractedConcept]
    # Phase 1.5 verifier 가 채우는 환각/오인용 fact 분리 목록.
    # 캐시된 raw LLM 응답에는 없으므로 default 비워두고, parse 후 verifier 가 주입.
    verification_failures: list[dict] = Field(default_factory=list)


class RegistryEntry(BaseModel):
    """엔티티/개념 레지스트리 항목"""

    id: str  # entity-001, concept-001
    name_ko: str
    aliases: list[str] = Field(default_factory=list)
    type: str  # person, org, place, other (entity) / topic (concept)
    source_ids: list[str] = Field(default_factory=list)
    source_page_map: dict[str, list[int]] = Field(default_factory=dict)
    file: str  # relative path from wiki_output/


class Registry(BaseModel):
    """엔티티 또는 개념 레지스트리"""

    entries: dict[str, RegistryEntry] = Field(default_factory=dict)
    name_index: dict[str, str] = Field(default_factory=dict)  # name_ko/alias → id
    next_id: int = 1
    prefix: str = "entity"  # entity or concept

    def _plural_prefix(self) -> str:
        if self.prefix.endswith("y"):
            return self.prefix.rstrip("y") + "ies"
        return self.prefix + "s"

    def find_by_name(self, name: str) -> RegistryEntry | None:
        entry_id = self.name_index.get(name)
        if entry_id:
            return self.entries.get(entry_id)
        return None

    def register(
        self,
        name_ko: str,
        type: str,
        aliases: list[str] | None = None,
        source_id: str = "",
        pages: list[int] | None = None,
    ) -> RegistryEntry:
        entry_id = f"{self.prefix}-{self.next_id:03d}"
        self.next_id += 1
        source_page_map: dict[str, list[int]] = {}
        if source_id and pages:
            source_page_map[source_id] = sorted(set(pages))
        entry = RegistryEntry(
            id=entry_id,
            name_ko=name_ko,
            aliases=aliases or [],
            type=type,
            source_ids=[source_id] if source_id else [],
            source_page_map=source_page_map,
            file=f"{self._plural_prefix()}/{entry_id}.md",
        )
        self.entries[entry_id] = entry
        self.name_index[name_ko] = entry_id
        for alias in entry.aliases:
            self.name_index[alias] = entry_id
        return entry

    def add_source(
        self,
        entry_id: str,
        source_id: str,
        pages: list[int] | None = None,
    ) -> None:
        entry = self.entries.get(entry_id)
        if not entry:
            return
        if source_id not in entry.source_ids:
            entry.source_ids.append(source_id)
        if pages:
            existing = set(entry.source_page_map.get(source_id, []))
            existing.update(pages)
            entry.source_page_map[source_id] = sorted(existing)

    def add_alias(self, entry_id: str, alias: str) -> None:
        entry = self.entries.get(entry_id)
        if entry and alias not in entry.aliases:
            entry.aliases.append(alias)
            self.name_index[alias] = entry_id


class ProgressState(BaseModel):
    """파이프라인 진행 상태"""

    phase: str = "init"
    last_processed_index: int = -1
    total_documents: int = 0
    phase1_completed: bool = False
    phase2_completed: bool = False
    phase3_completed: bool = False
    phase4_completed: bool = False
    phase5_completed: bool = False
    phase6_completed: bool = False
    phase7_completed: bool = False
    updated_at: datetime = Field(default_factory=datetime.now)
