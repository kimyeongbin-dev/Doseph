"""DTO 노출/유입 최소화 회귀 테스트 (로드맵 ⑤-3).

응답 DTO는 클라이언트에 **꼭 필요한 필드만** 노출해야 한다. 특히 소프트삭제 내부필드
`deleted_at` 은 응답에 나오면 안 된다(이미 삭제된 행은 응답 자체에 없음). 요청 DTO는
서버가 auth 에서 정하는 소유자 필드(account_id)를 받지 않아야 한다(mass-assignment 방지).
"""

from app.dtos.challenge import ChallengeResponse
from app.dtos.chat_session import ChatSessionResponse
from app.dtos.medication import MedicationResponse
from app.dtos.message import MessageResponse
from app.dtos.oauth import AuthMeResponse
from app.dtos.profile import ProfileCreate, ProfileResponse, ProfileSummaryResponse


class TestResponseHidesDeletedAt:
    """응답 DTO 에 소프트삭제 내부필드 deleted_at 이 노출되지 않아야 한다."""

    def test_profile_response(self) -> None:
        assert "deleted_at" not in ProfileResponse.model_fields

    def test_chat_session_response(self) -> None:
        assert "deleted_at" not in ChatSessionResponse.model_fields

    def test_challenge_response(self) -> None:
        assert "deleted_at" not in ChallengeResponse.model_fields

    def test_medication_response(self) -> None:
        assert "deleted_at" not in MedicationResponse.model_fields

    def test_message_response(self) -> None:
        assert "deleted_at" not in MessageResponse.model_fields


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
