"""Unit tests for LifestyleGuideService.enqueue_guide_generation().

⚠️ 2026-09-15 전면 재작성 (QA-27).

    이 파일은 원래 **동기 생성** `generate_guide()` 를 향한 TDD Red 단계 테스트였다
    (2026-04-29 작성, docstring 에 *"intentionally RED until the module is implemented"*).
    이후 가이드 생성이 **큐 기반**으로 재설계되면서 그 메서드는 사라졌는데,
    이 파일이 CI 에서 한 번도 돌지 않아 **4개월 반 동안 빨간 채 방치**됐다.

    즉 "고장난 테스트"가 아니라 **"사라진 기능을 테스트하는 테스트"** 였다.
    이름만 바꿔 되살리면 없는 기능을 되살리는 압력이 생기므로, 현재 계약으로 다시 썼다.

옛 의도 중 살린 것 / 버린 것:

    ✅ 살림 — LifestyleGuide 반환 · 저장 호출 · medication_snapshot 구성 · active 약 없음 예외
    ❌ 버림 — LLM 1회 호출 · 챌린지 bulk 생성 · LLM 오류/JSON 파싱 실패
              → 전부 **RQ 워커의 책임**으로 이동했다. 서비스는 이제 enqueue 까지만 한다.

이 파일이 잠그는 계약:
    (1) 그룹 미존재 404 / 남의 그룹 403 / active 약 0건 409
    (2) **fingerprint dedupe** — 같은 입력이면 기존 ready 를 그대로 돌려주고
        pending 생성도 enqueue 도 하지 않는다 (LLM 비용 절감 계약)
    (3) dedupe miss 면 pending 을 만들고 큐에 넣는다. snapshot 에 약이 모두 담긴다

이 파일이 단언하지 않는 것:
    실제 LLM 응답·챌린지 생성·SSE 스트림. 워커와 `stream_guide_states` 의 몫이다.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.services.lifestyle_guide_service import LifestyleGuideService


def _make_medication(name: str = "타이레놀정500mg") -> MagicMock:
    med = MagicMock()
    med.medicine_name = name
    med.dose_per_intake = "1정"
    med.daily_intake_count = 3
    med.intake_times = ["08:00", "13:00", "19:00"]
    return med


def _make_group(profile_id) -> MagicMock:
    group = MagicMock()
    group.id = uuid4()
    group.profile_id = profile_id
    return group


@pytest.fixture
def service() -> LifestyleGuideService:
    """협력자를 전부 대역으로 세운 서비스. 큐도 대역이라 실제 Redis 를 쓰지 않는다."""
    svc = LifestyleGuideService()
    svc.prescription_group_repo = MagicMock()
    svc.medication_repo = MagicMock()
    svc.profile_repo = MagicMock()
    svc.guide_repo = MagicMock()
    svc._queue = MagicMock()
    return svc


# ── 진입 검증 — 404 / 403 / 409 ───────────────────────────────────────────────
# 흐름: 그룹 조회 -> 소유 확인 -> active 약 확인. 셋 다 통과해야 생성으로 넘어간다.


async def test_missing_prescription_group_raises_404(service: LifestyleGuideService) -> None:
    service.prescription_group_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as raised:
        await service.enqueue_guide_generation(uuid4(), uuid4())

    assert raised.value.status_code == 404


async def test_foreign_prescription_group_raises_403(service: LifestyleGuideService) -> None:
    """남의 처방전 그룹으로 가이드를 만들 수 없다 — 보안 경계."""
    group = _make_group(profile_id=uuid4())
    service.prescription_group_repo.get_by_id = AsyncMock(return_value=group)

    with pytest.raises(HTTPException) as raised:
        await service.enqueue_guide_generation(uuid4(), group.id)

    assert raised.value.status_code == 403


async def test_no_active_medication_raises_409(service: LifestyleGuideService) -> None:
    """약이 없으면 만들 가이드도 없다 — 409 로 명확히 거절한다."""
    profile_id = uuid4()
    group = _make_group(profile_id=profile_id)
    service.prescription_group_repo.get_by_id = AsyncMock(return_value=group)
    service.medication_repo.get_active_by_prescription_group = AsyncMock(return_value=[])

    with pytest.raises(HTTPException) as raised:
        await service.enqueue_guide_generation(profile_id, group.id)

    assert raised.value.status_code == 409
    assert "NO_ACTIVE_MEDICATIONS" in str(raised.value.detail)


# ── ⭐ fingerprint dedupe — 이 파일에서 가장 값진 계약 ────────────────────────
# 흐름: 약 snapshot + health_survey -> fingerprint -> 같은 ready 가이드가 있으면 그대로 반환
# 같은 입력에 LLM 을 다시 태우지 않겠다는 **비용 계약**이라, 단순 반환값이 아니라
# "pending 을 만들지 않았고 큐에도 넣지 않았다"까지 단언한다.


async def test_dedupe_hit_returns_existing_without_enqueue(service: LifestyleGuideService) -> None:
    profile_id = uuid4()
    group = _make_group(profile_id=profile_id)
    existing = MagicMock(id=uuid4())

    service.prescription_group_repo.get_by_id = AsyncMock(return_value=group)
    service.medication_repo.get_active_by_prescription_group = AsyncMock(return_value=[_make_medication()])
    service.profile_repo.get_by_id = AsyncMock(return_value=MagicMock(health_survey=None))
    service.guide_repo.get_ready_by_fingerprint = AsyncMock(return_value=existing)
    service.guide_repo.create_pending = AsyncMock()

    result = await service.enqueue_guide_generation(profile_id, group.id)

    assert result is existing, "같은 입력이면 기존 ready 가이드를 그대로 돌려줘야 한다"
    service.guide_repo.create_pending.assert_not_awaited()
    service._queue.enqueue.assert_not_called(), "dedupe hit 인데 큐에 넣으면 LLM 비용이 다시 든다"


async def test_dedupe_miss_creates_pending_and_enqueues(service: LifestyleGuideService) -> None:
    profile_id = uuid4()
    group = _make_group(profile_id=profile_id)
    pending = MagicMock(id=uuid4())

    service.prescription_group_repo.get_by_id = AsyncMock(return_value=group)
    service.medication_repo.get_active_by_prescription_group = AsyncMock(return_value=[_make_medication()])
    service.profile_repo.get_by_id = AsyncMock(return_value=MagicMock(health_survey=None))
    service.guide_repo.get_ready_by_fingerprint = AsyncMock(return_value=None)
    service.guide_repo.create_pending = AsyncMock(return_value=pending)

    result = await service.enqueue_guide_generation(profile_id, group.id)

    assert result is pending
    service.guide_repo.create_pending.assert_awaited_once()
    service._queue.enqueue.assert_called_once()
    assert str(pending.id) in service._queue.enqueue.call_args.args, (
        "큐 작업에 대상 guide_id 가 실려야 워커가 무엇을 만들지 안다"
    )


# ── medication_snapshot — 약이 빠짐없이 담기는가 ─────────────────────────────
# 흐름: active 약 목록 -> snapshot dict 목록 -> create_pending 인자로 전달
# 옛 테스트의 의도를 그대로 이어받은 항목이다(설계가 바뀌어도 이 계약은 유효).


async def test_snapshot_contains_every_active_medication(service: LifestyleGuideService) -> None:
    profile_id = uuid4()
    group = _make_group(profile_id=profile_id)
    meds = [_make_medication("타이레놀정500mg"), _make_medication("오메프라졸캡슐")]

    service.prescription_group_repo.get_by_id = AsyncMock(return_value=group)
    service.medication_repo.get_active_by_prescription_group = AsyncMock(return_value=meds)
    service.profile_repo.get_by_id = AsyncMock(return_value=MagicMock(health_survey=None))
    service.guide_repo.get_ready_by_fingerprint = AsyncMock(return_value=None)
    service.guide_repo.create_pending = AsyncMock(return_value=MagicMock(id=uuid4()))

    await service.enqueue_guide_generation(profile_id, group.id)

    snapshot = service.guide_repo.create_pending.call_args.kwargs["medication_snapshot"]
    names = [entry.get("medicine_name") for entry in snapshot]
    assert names == ["타이레놀정500mg", "오메프라졸캡슐"], f"active 약이 snapshot 에 모두 담겨야 한다 — 실제: {names}"


# ── fingerprint 가 입력 변화를 실제로 반영하는가 ─────────────────────────────
# 흐름: 약 구성이 다르면 fingerprint 도 달라야 dedupe 가 오작동하지 않는다
# 이게 깨지면 "다른 약인데 남의 가이드를 돌려주는" 조용한 사고가 난다.


async def test_different_medications_produce_different_fingerprint(service: LifestyleGuideService) -> None:
    profile_id = uuid4()
    group = _make_group(profile_id=profile_id)
    service.prescription_group_repo.get_by_id = AsyncMock(return_value=group)
    service.profile_repo.get_by_id = AsyncMock(return_value=MagicMock(health_survey=None))
    service.guide_repo.get_ready_by_fingerprint = AsyncMock(return_value=None)
    service.guide_repo.create_pending = AsyncMock(return_value=MagicMock(id=uuid4()))

    fingerprints = []
    for names in (["타이레놀정500mg"], ["오메프라졸캡슐"]):
        service.medication_repo.get_active_by_prescription_group = AsyncMock(
            return_value=[_make_medication(n) for n in names]
        )
        await service.enqueue_guide_generation(profile_id, group.id)
        fingerprints.append(service.guide_repo.create_pending.call_args.kwargs["input_fingerprint"])

    assert fingerprints[0] != fingerprints[1], (
        "약 구성이 다른데 fingerprint 가 같으면 남의 가이드를 dedupe 로 돌려주게 된다"
    )
