"""API 전용 CSP + 리포팅 헤더 회귀 테스트 (로드맵5 H1).

API 응답은 JSON 만 반환하고 HTML/스크립트를 서빙하지 않으므로, 문서 CSP(FE 정적 _headers)와
분리된 **가장 엄격한 API 전용 CSP**(default-src 'none')를 모든 응답에 싣는다. 위반 리포트는
2026 표준(report-to + Reporting-Endpoints)에 하위호환(report-uri)을 병행해 수집한다.
"""

from httpx import AsyncClient
import pytest

from app.middlewares.security import build_api_csp


class TestBuildApiCsp:
    """순수 함수 build_api_csp: 정책 문자열 조립 규칙."""

    def test_baseline_directives_present(self) -> None:
        """리포트 URI 없이 호출 시 엄격 기본 지시어 3종을 포함한다."""
        csp = build_api_csp()

        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'none'" in csp

    def test_without_report_uri_omits_reporting_directives(self) -> None:
        """리포트 URI 미지정 시 report-to/report-uri 지시어를 넣지 않는다."""
        csp = build_api_csp()

        assert "report-uri" not in csp
        assert "report-to" not in csp

    def test_with_report_uri_adds_both_reporting_directives(self) -> None:
        """리포트 URI 지정 시 report-uri(하위호환) + report-to(2026 표준) 병행."""
        report_uri = "https://api.example.com/api/v1/security/csp-report"
        csp = build_api_csp(report_uri=report_uri)

        assert f"report-uri {report_uri}" in csp
        assert "report-to csp-endpoint" in csp


class TestApiCspResponseHeaders:
    """실제 API 응답에 CSP + Reporting-Endpoints 헤더가 실리는지 가드."""

    @pytest.mark.asyncio
    async def test_response_carries_api_csp_header(self, client: AsyncClient) -> None:
        """임의 API 응답(health)에 Content-Security-Policy(엄격) 헤더가 있어야 한다."""
        response = await client.get("/api/v1/health")

        csp = response.headers.get("content-security-policy")
        assert csp is not None
        assert "default-src 'none'" in csp

    @pytest.mark.asyncio
    async def test_response_carries_reporting_endpoints_header(self, client: AsyncClient) -> None:
        """Reporting API 엔드포인트 선언(Reporting-Endpoints) 헤더가 있어야 한다."""
        response = await client.get("/api/v1/health")

        reporting = response.headers.get("reporting-endpoints")
        assert reporting is not None
        assert "csp-endpoint=" in reporting
