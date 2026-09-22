from pydantic import BaseModel, Field


class DrugInteraction(BaseModel):
    """One drug-to-drug interaction entry."""

    drug: str = Field(description="상호작용 약품명")
    description: str = Field(description="상호작용 설명")


class PrecautionSection(BaseModel):
    """식약처 NB_DOC_DATA 카테고리 1개 — drug-info 응답의 warnings 항목.

    Examples:
        {"category": "경고", "items": ["임산부는 신중히 투여", "..."]}
        {"category": "임부에 대한 투여", "items": ["..."]}
    """

    category: str = Field(description="식약처 카테고리 (예: 경고, 금기, 신중 투여)")
    items: list[str] = Field(default_factory=list, description="해당 카테고리의 PARAGRAPH 목록")


class DrugInfoResponse(BaseModel):
    """Aggregated drug information returned to the client."""

    medicine_name: str = Field(description="약품명")
    warnings: list[PrecautionSection] = Field(
        default_factory=list,
        description="식약처 카테고리별 주의사항 (이상반응 제외 9 카테고리)",
    )
    side_effects: list[str] = Field(default_factory=list, description="이상반응 (NB '4. 이상반응')")
    dosage: str = Field(default="", description="용법용량 평문 (UD_DOC_DATA)")
    interactions: list[DrugInteraction] = Field(
        default_factory=list,
        description="약물 상호작용 (현재 별도 마스터 미수집 — 항상 빈 배열)",
    )
    severe_reaction_advice: str = Field(
        default="심한 부작용이 나타나면 즉시 복용을 중단하고 의사와 상담하세요.",
        description="심각한 반응 시 조언",
    )
