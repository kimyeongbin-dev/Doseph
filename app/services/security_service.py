"""CSP 위반 리포트 파싱·로깅 서비스.

브라우저가 보내는 두 형식(레거시 report-uri, 2026 Reporting API)을 하나의 정규화된
위반 목록으로 변환하고, 로거로 남긴다(핸들러의 ScrubFilter 가 민감패턴을 자동 마스킹).
프레임워크에 의존하지 않는 순수 로직이라 단위 테스트가 용이하다.
"""

import logging
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

# 정규화 필드 -> (레거시 kebab-case 키, Reporting API camelCase 키)
_FIELD_ALIASES: dict[str, tuple[str, str]] = {
    "document_uri": ("document-uri", "documentURL"),
    "violated_directive": ("violated-directive", "violatedDirective"),
    "effective_directive": ("effective-directive", "effectiveDirective"),
    "blocked_uri": ("blocked-uri", "blockedURL"),
}

# URL 값인 필드(query·fragment 에 토큰·PII 가능 -> 로깅 전 제거 대상)
_URL_FIELDS = frozenset({"document_uri", "blocked_uri"})


def _strip_query(value: str) -> str:
    """Drop query/fragment from a URL value; return non-URL values unchanged."""
    parts = urlsplit(value)
    if parts.scheme and parts.netloc:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return value


class CspReportService:
    """브라우저 CSP 위반 리포트를 정규화하고 로깅한다."""

    # ── CSP 리포트 정규화 ──────────────────────────────────────────────
    # 흐름: 형식 판별(레거시 dict / Reporting API list) -> 위반 본문 추출 -> 필드 정규화
    def parse_violations(self, payload: dict | list) -> list[dict[str, str]]:
        """Normalize a CSP report payload into a list of violation dicts.

        Args:
            payload: Parsed JSON body (legacy dict or Reporting API list).

        Returns:
            list[dict[str, str]]: Normalized violations; empty if unrecognized.
        """
        if isinstance(payload, dict):
            report = payload.get("csp-report")
            if not isinstance(report, dict):
                return []
            normalized = self._normalize(report)
            return [normalized] if normalized else []

        if isinstance(payload, list):
            violations: list[dict[str, str]] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                body = item.get("body")
                if isinstance(body, dict):
                    normalized = self._normalize(body)
                    if normalized:
                        violations.append(normalized)
            return violations

        return []

    # ── CSP 위반 로깅 ──────────────────────────────────────────────────
    # 흐름: 위반별 WARNING (ScrubFilter 자동 마스킹 + request_id 컨텍스트)
    def log_violations(self, violations: list[dict[str, str]]) -> None:
        """Log each normalized violation at WARNING level.

        Args:
            violations: Normalized violation dicts from parse_violations.
        """
        for violation in violations:
            logger.warning(
                "CSP violation: directive=%s blocked=%s document=%s",
                violation.get("violated_directive", "-"),
                violation.get("blocked_uri", "-"),
                violation.get("document_uri", "-"),
            )

    def _normalize(self, report: dict) -> dict[str, str]:
        """Extract known fields from a raw violation dict (either key style)."""
        normalized: dict[str, str] = {}
        for canonical, (legacy_key, api_key) in _FIELD_ALIASES.items():
            value = report.get(legacy_key) or report.get(api_key)
            if value is not None:
                text = str(value)
                normalized[canonical] = _strip_query(text) if canonical in _URL_FIELDS else text
        return normalized
