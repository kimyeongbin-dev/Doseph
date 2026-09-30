"""Lifestyle guide RQ jobs — FastAPI 가 ``ai`` 큐로 enqueue 하는 진입점.

본 모듈은 RQ task entry point 만 정의한다. 실제 LLM 호출은 도메인 안의
``guide_generator`` 가 담당, DB 영속화는 ``LifestyleGuideRepository`` 가 담당한다.

흐름: pending guide 조회 -> [Tortoise lifecycle] 처방전 그룹 active 약물 재조회
       -> Profile.health_survey 조회 -> LLM 호출 (약물+건강정보)
       -> 결과 파싱 -> guide UPDATE(content+ready) -> 추천 챌린지 bulk INSERT
       (챌린지에도 prescription_group_id 동시 기록 → /challenge 페이지 분류용)
"""

import asyncio
import os
from uuid import UUID

from openai import AsyncOpenAI
from tortoise import Tortoise

from ai_worker.core.logger import get_logger
from ai_worker.domains.lifestyle.guide_generator import generate_guide_payload
from app.db.databases import TORTOISE_ORM
from app.dtos.lifestyle_guide import LlmGuideResponse
from app.models.lifestyle_guide import LifestyleGuideStatusValue
from app.models.medication import Medication
from app.repositories.challenge_repository import ChallengeRepository
from app.repositories.lifestyle_guide_repository import LifestyleGuideRepository
from app.repositories.medication_repository import MedicationRepository
from app.repositories.profile_repository import ProfileRepository

logger = get_logger(__name__)


def process_lifestyle_guide_task(guide_id: str, profile_id: str) -> bool:
  """[RQ Task] 라이프스타일 가이드 LLM 생성 + DB UPDATE.

  Args:
      guide_id: FastAPI 가 INSERT 한 pending ``lifestyle_guides.id`` (UUID 문자열).
      profile_id: 가이드 소유 프로필 ID.

  Returns:
      성공 시 ``True`` — terminal status (ready/no_active_meds) 도달.
      예외 발생 시 ``False`` — status='failed' 로 기록.
  """
  logger.info("Starting lifestyle guide task: guide_id=%s profile_id=%s", guide_id, profile_id)
  try:
    return asyncio.run(_run_pipeline(guide_id, profile_id))
  except Exception:
    logger.exception("Lifestyle guide task failed for %s", guide_id)
    try:
      asyncio.run(_persist_terminal(guide_id, LifestyleGuideStatusValue.FAILED))
    except Exception:
      logger.exception("Failed to persist FAILED terminal status for %s", guide_id)
    return False


async def _run_pipeline(guide_id: str, profile_id: str) -> bool:
  """Tortoise lifecycle 한 번 안에서 처방전 그룹 active 약물 + 건강정보 + LLM."""
  await Tortoise.init(config=TORTOISE_ORM)
  try:
    med_repo = MedicationRepository()
    guide_repo = LifestyleGuideRepository()
    challenge_repo = ChallengeRepository()
    profile_repo = ProfileRepository()

    guide = await guide_repo.get_by_id(UUID(guide_id))
    if guide is None:
      logger.warning("[GUIDE] pending guide vanished guide_id=%s", guide_id)
      return True

    # v3: 처방전 그룹 단위. 옛 호출 (group_id NULL) 은 fallback 으로 프로필 전체.
    group_id = getattr(guide, "prescription_group_id", None)
    if group_id is not None:
      meds = await med_repo.get_active_by_prescription_group(group_id)
    else:
      meds = await med_repo.get_active_by_profile(UUID(profile_id))

    if not meds:
      logger.warning(
        "[GUIDE] no active meds at worker time profile_id=%s group_id=%s",
        profile_id,
        group_id,
      )
      await guide_repo.mark_terminal(guide_id, LifestyleGuideStatusValue.NO_ACTIVE_MEDS)
      return True

    profile = await profile_repo.get_by_id(UUID(profile_id))
    health_survey = profile.health_survey if profile else None

    med_dicts = [_med_to_dict(m) for m in meds]
    client = _build_openai_client()
    parsed = await generate_guide_payload(med_dicts, health_survey, client)
    await _persist_ready(
      guide_repo,
      challenge_repo,
      guide_id,
      profile_id,
      parsed,
      prescription_group_id=group_id,
    )
    return True
  finally:
    await Tortoise.close_connections()


async def _persist_ready(
  guide_repo: LifestyleGuideRepository,
  challenge_repo: ChallengeRepository,
  guide_id: str,
  profile_id: str,
  parsed: LlmGuideResponse,
  *,
  prescription_group_id: UUID | None,
) -> None:
  """LLM 결과를 guide UPDATE + 추천 챌린지 bulk INSERT (group_id 동시 기록)."""
  content = parsed.model_dump(exclude={"recommended_challenges"})
  updated = await guide_repo.mark_ready(guide_id, content)
  if updated == 0:
    logger.warning("[GUIDE] guide_id=%s vanished before mark_ready (deleted by user?)", guide_id)
    return
  await challenge_repo.bulk_create_from_guide(
    guide_id=guide_id,
    profile_id=profile_id,
    challenges=parsed.recommended_challenges,
    prescription_group_id=prescription_group_id,
  )
  logger.info(
    "[GUIDE] worker complete guide_id=%s challenges=%d group_id=%s",
    guide_id,
    len(parsed.recommended_challenges),
    prescription_group_id,
  )


async def _persist_terminal(guide_id: str, status: LifestyleGuideStatusValue) -> None:
  """예외 경로 — Tortoise lifecycle 별도로 열어 terminal status 기록."""
  await Tortoise.init(config=TORTOISE_ORM)
  try:
    await LifestyleGuideRepository().mark_terminal(guide_id, status)
  finally:
    await Tortoise.close_connections()


def _build_openai_client() -> AsyncOpenAI:
  """Worker 인스턴스 단위 OpenAI 클라이언트 — env 미설정 시 즉시 실패."""
  api_key = os.environ.get("OPENAI_API_KEY")
  if not api_key:
    raise ValueError("OPENAI_API_KEY 가 설정되지 않았습니다.")
  return AsyncOpenAI(api_key=api_key)


def _med_to_dict(med: Medication) -> dict:
  """Medication ORM -> snapshot/prompt 안전한 dict.

  FastAPI 측 ``LifestyleGuideService._med_to_dict`` 와 동기화 — 두 곳 모두
  처방일 / 시작일 / 종료일 ISO 문자열을 포함해야 FE 가 가이드 안내 배너에
  처방일 라벨을 그릴 수 있다.
  """
  return {
    "medicine_name": med.medicine_name,
    "category": getattr(med, "category", None),
    "intake_instruction": getattr(med, "intake_instruction", None),
    "dose_per_intake": getattr(med, "dose_per_intake", None),
    "dispensed_date": med.dispensed_date.isoformat() if med.dispensed_date else None,
    "start_date": med.start_date.isoformat() if med.start_date else None,
    "end_date": med.end_date.isoformat() if med.end_date else None,
  }
