"""API v1 routes module.

This module aggregates all v1 API routes and creates the main v1 router
for the FastAPI application.
"""

from fastapi import APIRouter

from app.apis.v1.challenge_routers import router as challenge_router
from app.apis.v1.chat_session_routers import router as chat_session_router
from app.apis.v1.daily_log_routers import router as daily_log_router
from app.apis.v1.health_routers import router as health_router
from app.apis.v1.intake_log_routers import router as intake_log_router
from app.apis.v1.lifestyle_guide_routers import router as lifestyle_guide_router
from app.apis.v1.medication_routers import router as medication_router
from app.apis.v1.medicine_search_routers import router as medicine_search_router
from app.apis.v1.message_routers import router as message_router
from app.apis.v1.mock_oauth_routers import mock_router
from app.apis.v1.oauth_routers import oauth_router
from app.apis.v1.ocr_routers import router as ocr_router
from app.apis.v1.prescription_group_routers import router as prescription_group_router
from app.apis.v1.profile_routers import router as profile_router
from app.apis.v1.security_routers import router as security_router
from app.core import config
from app.core.config import Env

# Main v1 API router
v1_routers = APIRouter(prefix="/api/v1")

# Include all sub-routers
v1_routers.include_router(health_router)
v1_routers.include_router(challenge_router)
v1_routers.include_router(daily_log_router)
v1_routers.include_router(intake_log_router)
v1_routers.include_router(lifestyle_guide_router)
v1_routers.include_router(medication_router)
v1_routers.include_router(medicine_search_router)
v1_routers.include_router(oauth_router)
v1_routers.include_router(profile_router)
v1_routers.include_router(chat_session_router)
v1_routers.include_router(message_router)
v1_routers.include_router(ocr_router)
v1_routers.include_router(prescription_group_router)
v1_routers.include_router(security_router)

# ── mock IdP(카카오) 라우터: 로컬 전용 등록 ──────────────────────────
# 흐름: ENV 확인 -> local 일 때만 /api/v1/mock/kakao/* 등록
# mock OAuth 는 개발·E2E 용 테스트 대역이다. 프로덕션에 노출되면 세션 위조로
# 이어지지 않더라도(프로드 토큰 교환은 실제 카카오로 나감) 불필요한 공격 표면이므로
# 환경 게이팅한다. dev 로그인 백도어를 제거한 것과 같은 원칙.
if config.ENV == Env.LOCAL:
    v1_routers.include_router(mock_router)
