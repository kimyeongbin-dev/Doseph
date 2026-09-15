"""Prescription group model module.

처방전 단위의 SSOT (Single Source of Truth). 한 번의 의료 진료/처방으로 묶이는
약물들 + 그 처방전 컨텍스트에서 만들어진 가이드/챌린지가 모두 본 그룹 ID 로
연결된다. OCR confirm 또는 수동 등록 1회 = ``PrescriptionGroup`` 1 row.

마이그레이션 #24 에서 기존 medication 들은 ``(profile_id, dispensed_date)``
기준으로 자동 그룹핑되어 source='MIGRATED' 로 채워진다. 기존 가이드/챌린지는
NULL 로 남으며 (= 옛 가이드는 처방전 컨텍스트 없음) 신규부터 group-bound.
"""

from enum import StrEnum

from tortoise import fields, models


class PrescriptionGroupSource(StrEnum):
    """처방전 그룹의 생성 경로.

    Attributes:
        OCR: 사용자가 처방전 이미지를 업로드 → CLOVA OCR → confirm 한 흐름.
        MANUAL: 사용자가 약품을 직접 입력으로 추가한 흐름.
        MIGRATED: 마이그레이션 #24 시점에 기존 medication 들로부터 산출된 그룹.
    """

    OCR = "OCR"
    MANUAL = "MANUAL"
    MIGRATED = "MIGRATED"


class PrescriptionGroup(models.Model):
    """처방전 그룹 — medication / lifestyle_guide / challenge 의 부모 단위.

    Attributes:
        id: Primary key UUID.
        profile: 처방전 소유 프로필 (소프트 삭제 시 cascade).
        department: 처방 진료과 (예: 내과). 같은 (profile, dispensed_date) 라도
            진료과는 group 메타에 단일 값으로 박힌다 (가장 흔한 값).
        dispensed_date: 처방 조제일 — 그룹 매핑 키.
        source: 생성 경로 (OCR / MANUAL / MIGRATED).
        created_at: 그룹 생성 시각.
    """

    id = fields.UUIDField(primary_key=True)
    profile = fields.ForeignKeyField(
        "models.Profile",
        related_name="prescription_groups",
        description="처방전 소유 프로필",
    )
    hospital_name = fields.CharField(max_length=128, null=True, description="처방전 발행 병원 이름")
    department = fields.CharField(max_length=64, null=True, description="처방 진료과 (내과/소아과 등)")
    dispensed_date = fields.DateField(null=True, description="처방 조제일 — 그룹 매핑 키")
    source = fields.CharField(
        max_length=16,
        default=PrescriptionGroupSource.OCR.value,
        description="생성 경로 (OCR/MANUAL/MIGRATED)",
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "prescription_groups"
        indexes = (("profile_id", "dispensed_date"),)
