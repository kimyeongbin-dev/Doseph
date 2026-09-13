"""CSP 위반 리포트 수집 엔드포인트 테스트 (로드맵5 H2).

브라우저는 두 형식으로 위반을 보고한다: 레거시 report-uri(`{"csp-report": {...}}`,
kebab-case 필드)와 2026 Reporting API(`[{"type": ..., "body": {...}}]`, camelCase 필드).
서비스는 둘 다 정규화하고, 라우터는 수신 시 마스킹 로깅 후 204 를 반환하며 형식이
전혀 맞지 않으면 400 을 준다. rate-limit 은 미들웨어(EXCLUDED 아님)가 자동 적용한다.
"""

from collections.abc import Iterator
import logging

from httpx import AsyncClient
import pytest

from app.services.security_service import CspReportService


class TestCspReportService:
    """순수 파싱 로직: 두 형식 → 정규화된 위반 목록."""

    def test_parse_legacy_report_uri_format(self) -> None:
        """레거시 {"csp-report": {...}} 형식(kebab-case)을 정규화한다."""
        service = CspReportService()
        payload = {
            "csp-report": {
                "document-uri": "https://doseph.com/dashboard",
                "violated-directive": "script-src-elem",
                "effective-directive": "script-src-elem",
                "blocked-uri": "https://evil.example.com/x.js",
            }
        }

        violations = service.parse_violations(payload)

        assert len(violations) == 1
        assert violations[0]["blocked_uri"] == "https://evil.example.com/x.js"
        assert violations[0]["violated_directive"] == "script-src-elem"
        assert violations[0]["document_uri"] == "https://doseph.com/dashboard"

    def test_parse_reporting_api_format(self) -> None:
        """Reporting API 배열 형식(camelCase body)을 정규화한다."""
        service = CspReportService()
        payload = [
            {
                "type": "csp-violation",
                "url": "https://doseph.com/dashboard",
                "body": {
                    "documentURL": "https://doseph.com/dashboard",
                    "violatedDirective": "script-src-elem",
                    "effectiveDirective": "script-src-elem",
                    "blockedURL": "https://evil.example.com/x.js",
                },
            }
        ]

        violations = service.parse_violations(payload)

        assert len(violations) == 1
        assert violations[0]["blocked_uri"] == "https://evil.example.com/x.js"
        assert violations[0]["violated_directive"] == "script-src-elem"

    def test_parse_invalid_payload_returns_empty(self) -> None:
        """형식이 전혀 맞지 않으면 빈 목록을 반환한다."""
        service = CspReportService()

        assert service.parse_violations({}) == []
        assert service.parse_violations({"foo": "bar"}) == []
        assert service.parse_violations([]) == []

    def test_url_fields_strip_query_string(self) -> None:
        """URL 필드(document/blocked)의 query·fragment 는 제거한다(민감정보 로깅 방지)."""
        service = CspReportService()
        payload = {
            "csp-report": {
                "document-uri": "https://doseph.com/dashboard?sid=secret#frag",
                "violated-directive": "connect-src",
                "blocked-uri": "https://evil.example.com/x?token=abcdef",
            }
        }

        violation = service.parse_violations(payload)[0]

        assert violation["document_uri"] == "https://doseph.com/dashboard"
        assert violation["blocked_uri"] == "https://evil.example.com/x"
        assert "?" not in violation["blocked_uri"]

    def test_non_url_blocked_uri_kept_as_is(self) -> None:
        """URL 이 아닌 blocked-uri(inline, eval 등)는 원본 그대로 둔다."""
        service = CspReportService()
        payload = {"csp-report": {"blocked-uri": "inline", "violated-directive": "script-src"}}

        violation = service.parse_violations(payload)[0]

        assert violation["blocked_uri"] == "inline"


@pytest.fixture
def app_caplog(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """'app' 로거는 setup_logger 가 propagate=False(root 중복 전달 방지)로 설정한다.

    caplog 핸들러는 root 에 붙으므로 전파가 끊긴 'app' 계열 로그를 못 잡는다. 실제
    서비스 로거 동작을 검증하려면 caplog 핸들러를 'app' 로거에 직접 부착한다.
    """
    app_logger = logging.getLogger("app")
    app_logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        app_logger.removeHandler(caplog.handler)


class TestLogViolations:
    """로깅 계약: 지시어 필드 폴백(violated → effective → '-')."""

    def test_effective_directive_used_when_violated_absent(self, app_caplog: pytest.LogCaptureFixture) -> None:
        """violated-directive 없이 effective-directive 만 온 위반도 지시어를 로그에 남긴다."""
        service = CspReportService()
        violations = [{"effective_directive": "script-src-elem", "blocked_uri": "inline"}]

        with app_caplog.at_level(logging.WARNING, logger="app"):
            service.log_violations(violations)

        assert "script-src-elem" in app_caplog.text
        assert "directive=-" not in app_caplog.text

    def test_violated_directive_preferred_over_effective(self, app_caplog: pytest.LogCaptureFixture) -> None:
        """둘 다 있으면 더 구체적인 violated-directive 를 우선한다(회귀 방지)."""
        service = CspReportService()
        violations = [{"violated_directive": "script-src", "effective_directive": "script-src-elem"}]

        with app_caplog.at_level(logging.WARNING, logger="app"):
            service.log_violations(violations)

        assert "directive=script-src " in app_caplog.text  # 후행 공백으로 -elem 접미 배제

    def test_dash_when_no_directive_field(self, app_caplog: pytest.LogCaptureFixture) -> None:
        """지시어 필드가 전혀 없으면 '-' 로 안전 수렴한다."""
        service = CspReportService()
        violations = [{"blocked_uri": "inline"}]

        with app_caplog.at_level(logging.WARNING, logger="app"):
            service.log_violations(violations)

        assert "directive=-" in app_caplog.text


class TestCspReportEndpoint:
    """엔드포인트: 유효 리포트 204, 비정상 400."""

    @pytest.mark.asyncio
    async def test_legacy_report_returns_204(self, client: AsyncClient) -> None:
        """레거시 형식 수신 시 204 No Content."""
        response = await client.post(
            "/api/v1/security/csp-report",
            json={
                "csp-report": {
                    "document-uri": "https://doseph.com/",
                    "violated-directive": "script-src",
                    "effective-directive": "script-src",
                    "blocked-uri": "inline",
                }
            },
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_reporting_api_report_returns_204(self, client: AsyncClient) -> None:
        """Reporting API 배열 형식 수신 시 204 No Content."""
        response = await client.post(
            "/api/v1/security/csp-report",
            json=[
                {
                    "type": "csp-violation",
                    "body": {
                        "documentURL": "https://doseph.com/",
                        "violatedDirective": "script-src",
                        "effectiveDirective": "script-src",
                        "blockedURL": "inline",
                    },
                }
            ],
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_invalid_payload_returns_400(self, client: AsyncClient) -> None:
        """CSP 리포트 형식이 아니면 400 Bad Request."""
        response = await client.post("/api/v1/security/csp-report", json={"foo": "bar"})

        assert response.status_code == 400
