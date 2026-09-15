"""Medication model module.

This module defines the Medication model for storing prescription medication
information and intake schedules.
"""

from tortoise import fields, models


class Medication(models.Model):
    """Medication model for prescription tracking.

    This model stores prescription medication information including dosage,
    intake schedules, and prescription details.

    Attributes:
        id: Primary key UUID.
        profile: Foreign key to Profile model.
        medicine_name: Name of the medication.
        dose_per_intake: Dosage per intake (e.g., "1 tablet", "5ml").
        intake_instruction: Intake instructions.
        intake_times: Daily intake times as JSON array.
        total_intake_count: Total prescribed intake count.
        remaining_intake_count: Remaining intake count.
        start_date: Medication start date.
        end_date: Expected end date.
        dispensed_date: Medication dispensing date.
        expiration_date: Medication expiration date.
        is_active: Whether currently taking medication.
        created_at: Record creation timestamp.
        updated_at: Last update timestamp.
    """

    id = fields.UUIDField(pk=True)

    # Connected to profiles table
    profile = fields.ForeignKeyField("models.Profile", related_name="medications")

    # 처방전 그룹 — OCR confirm / 수동 등록 시점에 set. 마이그레이션 후 NOT NULL
    # 로 강제하지 않는 이유: 외부 이관 / 임시 row 등의 예외 케이스 대비.
    prescription_group = fields.ForeignKeyField(
        "models.PrescriptionGroup",
        related_name="medications",
        null=True,
        description="소속 처방전 그룹 (한 번의 진료/처방 단위)",
    )

    medicine_name = fields.CharField(max_length=128, description="약품명")
    department = fields.CharField(max_length=64, null=True, description="처방 진료과 (예: 내과)")
    category = fields.CharField(max_length=64, null=True, description="약품 분류 (예: 해열진통제)")
    dose_per_intake = fields.CharField(max_length=32, null=True, description="1회 복용량 (예: 1정, 5ml)")
    daily_intake_count = fields.IntField(null=True, description="1일 복용 횟수")
    total_intake_days = fields.IntField(null=True, description="총 복용 일수")
    intake_instruction = fields.CharField(max_length=256, null=True, description="복용 지시사항")
    # =========================================================================
    # [AI OCR 파이프라인 트래킹을 위한 신규 컬럼 — BE 감사/디버깅 전용]
    # FE 화면 노출 의도 없음. OCR LLM 매칭 정확도 분석/모니터링 + 추후 자동
    # 보정 룰 튜닝 시 baseline 데이터로 활용.
    # =========================================================================
    raw_ocr_name = fields.CharField(
        max_length=128, null=True, description="OCR이 인식한 날것의 텍스트 (수동 입력 시 null, BE 트래킹 전용)"
    )
    is_llm_corrected = fields.BooleanField(
        default=False, description="LLM 또는 퍼지 매칭으로 교정된 약품인지 여부 (BE 트래킹 전용)"
    )
    match_score = fields.FloatField(
        null=True, description="퍼지 매칭 또는 LLM 유사도/신뢰도 점수 (0.0 ~ 1.0, BE 트래킹 전용)"
    )
    # =========================================================================

    # Use PostgreSQL JSONB to store arrays like ["08:00", "13:00"]
    intake_times = fields.JSONField(description="Daily intake times list")

    total_intake_count = fields.IntField(description="Total prescribed intake count")
    remaining_intake_count = fields.IntField(description="Remaining intake count")

    start_date = fields.DateField(description="Medication start date")
    end_date = fields.DateField(null=True, description="Expected end date")
    dispensed_date = fields.DateField(null=True, description="Medication dispensing date")
    expiration_date = fields.DateField(null=True, description="Medication expiration date")

    is_active = fields.BooleanField(default=True, description="Currently taking medication")

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "medications"
        indexes = (("profile_id", "is_active"),)
