"""DTO 노출/유입 최소화 회귀 테스트 (로드맵 ⑤-3).

응답 DTO는 클라이언트에 **꼭 필요한 필드만** 노출해야 한다. 요청 DTO는
서버가 auth 에서 정하는 소유자 필드(account_id)를 받지 않아야 한다(mass-assignment 방지).

⚠️ 2026-09-15(QA-01): 여기 있던 *"응답 DTO 5개에 `deleted_at` 이 없다"* 5건을
**삭제하고 아래 1건으로 대체**했다. soft delete 를 전면 폐지하면서 컬럼도 모델 필드도
사라졌기 때문에, 그 5건은 **무슨 짓을 해도 빨개지지 않는 헛된 초록(V-A)** 이 됐다.

대신 **더 이른 곳**을 잠근다 — DTO 가 아니라 **모델**. 누군가 soft delete 를 되살리려
모델에 `deleted_at` 을 추가하는 순간 빨개진다. DTO 노출은 그 다음 문제다.
"""

from tortoise import Tortoise

from app.db.databases import TORTOISE_APP_MODELS
from app.dtos.challenge import ChallengeResponse, ChallengeUpdate
from app.dtos.chat_session import ChatSessionResponse
from app.dtos.intake_log import IntakeLogCreate
from app.dtos.message import MessageCreate
from app.dtos.oauth import AuthMeResponse
from app.dtos.profile import ProfileCreate, ProfileResponse, ProfileSummaryResponse


class TestNoModelReintroducesSoftDelete:
    """어떤 모델도 `deleted_at` 필드를 다시 가지면 안 된다 (QA-01)."""

    def test_no_registered_model_has_deleted_at(self) -> None:
        """등록된 전 모델에서 `deleted_at` 필드가 0개여야 한다.

        QA-01 로 soft delete 를 폐지하고 컬럼 7개를 드롭했다. 되살리려면
        **의도적인 결정과 마이그레이션**이 필요하다 — 실수로 필드 하나를 얹어
        장부와 FK CASCADE 가 서로를 덮는 상태로 돌아가지 않도록 여기서 막는다.
        """
        Tortoise.init_models(TORTOISE_APP_MODELS, "models")
        registered = {
            f"{app_label}.{name}": model
            for app_label, models in Tortoise.apps.items()
            for name, model in models.items()
        }

        # ⚠️ 이 단언이 없으면 모델 0개를 훑고도 초록이다 — 실제로 한 번 그렇게 됐다.
        #    "검사 대상이 실재하는가"를 먼저 묻는다(결핍 주입의 상시화).
        assert len(registered) >= 15, f"모델이 로드되지 않았다 — 검사 자체가 무의미: {len(registered)}개"

        offenders = [name for name, model in registered.items() if "deleted_at" in model._meta.fields_map]

        assert offenders == [], f"soft delete 가 되살아났다: {offenders}"


class TestResponseHidesAccountId:
    """응답 DTO 는 불필요한 내부 FK account_id 를 노출하지 않아야 한다.

    호출자는 auth 컨텍스트로 이미 자기 계정이며, 계정 식별이 필요하면 /auth/me
    (AuthMeResponse)에서 얻는다. 따라서 AuthMeResponse 만 account_id 를 유지한다.
    """

    def test_profile_response_no_account_id(self) -> None:
        assert "account_id" not in ProfileResponse.model_fields

    def test_profile_summary_response_no_account_id(self) -> None:
        assert "account_id" not in ProfileSummaryResponse.model_fields

    def test_chat_session_response_no_account_id(self) -> None:
        assert "account_id" not in ChatSessionResponse.model_fields

    def test_auth_me_keeps_account_id(self) -> None:
        # /auth/me 의 존재 이유 = 로그인 계정 id 반환 → 유지되어야 한다.
        assert "account_id" in AuthMeResponse.model_fields


class TestRequestRejectsOwnerField:
    """요청 DTO 는 서버가 auth 에서 정하는 account_id 를 입력으로 받지 않아야 한다."""

    def test_profile_create_no_account_id(self) -> None:
        assert "account_id" not in ProfileCreate.model_fields


class TestRequestRejectsServerDecidedFields:
    """요청 DTO 는 서버가 결정하는 필드를 입력으로 받지 않아야 한다 (과유입/계약 불일치 방지)."""

    def test_message_create_no_sender_type(self) -> None:
        # sender_type 은 서버가 USER 로 강제 — 클라가 ASSISTANT 로 위조 지정할 수 없어야 한다.
        assert "sender_type" not in MessageCreate.model_fields

    def test_intake_log_create_no_status_fields(self) -> None:
        # 생성 시 상태는 서버가 SCHEDULED 로 결정, 복용 완료/스킵은 /take·/skip 엔드포인트 담당.
        assert "intake_status" not in IntakeLogCreate.model_fields
        assert "taken_at" not in IntakeLogCreate.model_fields


class TestChallengeUpdateRejectsProgressFields:
    """ChallengeUpdate 는 진행 상태(서버 단독 관리)를 클라 입력으로 받지 않아야 한다.

    완료 날짜·진행 상태를 generic PATCH 로 직접 기록하면 완료/스트릭 위조가
    가능하므로, 체크오프는 전용 엔드포인트(POST /challenges/{id}/check)로만
    이뤄진다. 진행 상태는 서버가 단독으로 계산한다.
    """

    def test_no_challenge_status(self) -> None:
        assert "challenge_status" not in ChallengeUpdate.model_fields

    def test_no_completed_dates(self) -> None:
        assert "completed_dates" not in ChallengeUpdate.model_fields

    def test_response_still_exposes_progress(self) -> None:
        # 응답에는 진행 상태가 필요하다 (읽기 전용 — UI 3-상태 렌더링용).
        assert "challenge_status" in ChallengeResponse.model_fields
        assert "completed_dates" in ChallengeResponse.model_fields
