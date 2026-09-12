"""Security middleware module.

This module provides security middleware for input validation and security headers.
Includes attack pattern detection, suspicious pattern logging, and security header injection.

Note: CSP is recommended to be set in Next.js for SPA compatibility.
"""

from collections.abc import Callable
import logging
import re

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import config

logger = logging.getLogger(__name__)

# Clear attack patterns (logging + blocking)
ATTACK_PATTERNS: list[tuple[str, str]] = [
    # Path Traversal (clear attack)
    (r"\.\.[/\\]", "path_traversal"),
    (r"\.\.%2[fF]", "path_traversal_encoded"),
    # Null Byte Injection (clear attack)
    (r"%00", "null_byte"),
    (r"\x00", "null_byte"),
]

# Suspicious patterns (logging only, no blocking - ORM provides defense)
SUSPICIOUS_PATTERNS: list[tuple[str, str]] = [
    (r"('\s*OR\s+'?\s*'?\s*=|'\s*OR\s+1\s*=\s*1)", "sql_injection_suspect"),
    (r'("\s*OR\s+"?\s*"?\s*=|"\s*OR\s+1\s*=\s*1)', "sql_injection_suspect"),
    (r";\s*(DROP|DELETE|UPDATE|INSERT)\s+", "sql_injection_suspect"),
    (r"UNION\s+(ALL\s+)?SELECT", "sql_union_suspect"),
    (r"<script", "xss_suspect"),
    (r"javascript:", "xss_suspect"),
]

# Compiled patterns for performance
COMPILED_ATTACK_PATTERNS = [(re.compile(p, re.IGNORECASE), name) for p, name in ATTACK_PATTERNS]
COMPILED_SUSPICIOUS_PATTERNS = [(re.compile(p, re.IGNORECASE), name) for p, name in SUSPICIOUS_PATTERNS]

# Baseline security headers (CSP excluded — handled separately)
# 문서 CSP 는 FE 정적 _headers, API 전용 CSP 는 별도 주입 -> 여기선 공통 헤더만 관리.
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

# CSP 위반 리포트 수집 경로 (H2 라우터가 구현) + Reporting API 엔드포인트 이름.
CSP_REPORT_PATH = "/api/v1/security/csp-report"
CSP_REPORT_ENDPOINT_NAME = "csp-endpoint"


# ── API 전용 CSP 문자열 조립 ──────────────────────────────────────────
# 흐름: 엄격 기본 지시어 -> (report_uri 있으면) report-uri + report-to 부착
def build_api_csp(report_uri: str | None = None) -> str:
    """Build the API-only Content-Security-Policy string.

    API responses return JSON only (no HTML/scripts), so the strictest policy
    applies: nothing may be loaded, framed, or used as a base URI. When a report
    URI is given, both report-uri (legacy) and report-to (2026 Reporting API)
    directives are appended for broad browser compatibility.

    Args:
        report_uri: Absolute URL that receives CSP violation reports. When None,
            no reporting directives are added.

    Returns:
        str: The assembled CSP header value.
    """
    directives = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    if report_uri is None:
        return directives
    return f"{directives}; report-uri {report_uri}; report-to {CSP_REPORT_ENDPOINT_NAME}"


def check_attack_patterns(value: str) -> str | None:
    """Check for clear attack patterns (blocking targets).

    Args:
        value: Input value to check.

    Returns:
        str | None: Attack pattern name if found, None otherwise.
    """
    for pattern, name in COMPILED_ATTACK_PATTERNS:
        if pattern.search(value):
            return name
    return None


def check_suspicious_patterns(value: str) -> str | None:
    """Check for suspicious patterns (logging only).

    Args:
        value: Input value to check.

    Returns:
        str | None: Suspicious pattern name if found, None otherwise.
    """
    for pattern, name in COMPILED_SUSPICIOUS_PATTERNS:
        if pattern.search(value):
            return name
    return None


def scan_request_params(request: Request) -> tuple[str | None, str | None]:
    """Scan request parameters for attack and suspicious patterns.

    Args:
        request: FastAPI request object.

    Returns:
        tuple[str | None, str | None]: (attack_pattern, suspicious_pattern)
            Pattern names if found, None otherwise.
    """
    attack_found = None
    suspicious_found = None

    # Query Parameters
    for key, value in request.query_params.items():
        for v in [key, value]:
            if not attack_found:
                attack_found = check_attack_patterns(v)
            if not suspicious_found:
                suspicious_found = check_suspicious_patterns(v)

    # Path Parameters
    for value in request.path_params.values():
        if isinstance(value, str):
            if not attack_found:
                attack_found = check_attack_patterns(value)
            if not suspicious_found:
                suspicious_found = check_suspicious_patterns(value)

    return attack_found, suspicious_found


class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware for input validation and security headers.

    This middleware provides:
    1. Input validation with attack pattern detection
    2. Suspicious pattern logging
    3. Security header injection
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through security middleware.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler in chain.

        Returns:
            Response: Processed response with security headers.
        """
        # 1. Input validation
        attack_pattern, suspicious_pattern = scan_request_params(request)

        # Log suspicious patterns (no blocking)
        if suspicious_pattern:
            logger.warning(
                "Suspicious pattern detected: %s, path=%s, ip=%s",
                suspicious_pattern,
                request.url.path,
                request.client.host if request.client else "unknown",
            )

        # Block clear attack patterns
        if attack_pattern:
            logger.error(
                "Attack pattern blocked: %s, path=%s, ip=%s",
                attack_pattern,
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            return Response(
                content='{"detail":{"error":"invalid_input","error_description":"Invalid input detected."}}',
                status_code=400,
                media_type="application/json",
            )

        # 2. Process request
        response = await call_next(request)

        # 3. Add security headers
        self._add_security_headers(response)

        return response

    def _add_security_headers(self, response: Response) -> None:
        """Add baseline security headers to the response.

        CSP is intentionally handled outside this loop: the document CSP lives in
        the Cloudflare Pages ``_headers`` file (static export has no server to emit
        per-request headers), and the API-specific CSP is injected separately.

        Args:
            response: Response object to add headers to.
        """
        # ── 기본 보안 헤더 적용 ────────────────────────────────────────
        # 흐름: SECURITY_HEADERS 상수 순회 -> 응답 헤더에 주입
        for header_name, header_value in SECURITY_HEADERS.items():
            response.headers[header_name] = header_value

        # ── API 전용 CSP + 리포팅 헤더 주입 ────────────────────────────
        # 흐름: config.API_BASE_URL 로 리포트 URL 구성 -> 엄격 CSP + Reporting-Endpoints
        #       API_BASE_URL 미설정 시 리포팅 없이 CSP 만 적용.
        report_uri = f"{config.API_BASE_URL}{CSP_REPORT_PATH}" if config.API_BASE_URL else None
        response.headers["Content-Security-Policy"] = build_api_csp(report_uri)
        if report_uri:
            response.headers["Reporting-Endpoints"] = f'{CSP_REPORT_ENDPOINT_NAME}="{report_uri}"'
