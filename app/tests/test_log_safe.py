"""Tests for log-safety masking utils + scrub filter (B5).

- 명시적 마스킹(1차): 토큰/Authorization/JWT/전화/주민번호/이메일
- ScrubFilter(2차 안전망): 고신뢰 패턴만(JWT·Bearer·주민번호), 정상 메시지 불변(오탐0)
- lazy %(§9): args 병합 결과 보존
"""

import logging

from app.core.log_safe import (
    ScrubFilter,
    mask_authorization,
    mask_email,
    mask_phone,
    mask_rrn,
    mask_token,
)


def _record(msg: str, args: tuple = ()) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)


# ── 명시적 마스킹 함수 ─────────────────────────────────────────────────
def test_mask_token_hides_value() -> None:
    """토큰은 값 전체를 숨긴다(원문 흔적 없음)."""
    out = mask_token("abcdef1234567890XYZ")
    assert "abcdef" not in out
    assert "***" in out


def test_mask_authorization_keeps_scheme_only() -> None:
    """Authorization 은 스킴만 남기고 자격증명은 마스킹."""
    assert mask_authorization("Bearer eyJhbGci.payload.sig") == "Bearer ***"


def test_mask_phone_masks_middle() -> None:
    """전화번호는 가운데 자리를 마스킹."""
    assert mask_phone("010-1234-5678") == "010-****-5678"


def test_mask_rrn_masks_back() -> None:
    """주민등록번호는 뒷자리 7자리를 마스킹."""
    assert mask_rrn("900101-1234567") == "900101-*******"


def test_mask_email_keeps_first_char_and_domain() -> None:
    """이메일은 로컬파트 첫 글자 + 도메인만 남긴다."""
    assert mask_email("alice@doseph.com") == "a***@doseph.com"


# ── ScrubFilter(2차 안전망) ────────────────────────────────────────────
def test_scrub_filter_masks_jwt() -> None:
    """메시지 속 JWT(eyJ….….…)는 스크럽된다."""
    rec = _record("resp token=eyJhbGciOiJI.eyJzdWIiOiIx.SflKxwRJSMeKKF2QT")
    ScrubFilter().filter(rec)
    out = rec.getMessage()
    assert "eyJhbGciOiJI" not in out
    assert "***" in out


def test_scrub_filter_masks_bearer() -> None:
    """Authorization: Bearer <tok> 의 토큰이 스크럽된다."""
    rec = _record("headers Authorization: Bearer abc123def456ghi789")
    ScrubFilter().filter(rec)
    out = rec.getMessage()
    assert "abc123def456" not in out
    assert "***" in out


def test_scrub_filter_masks_rrn() -> None:
    """메시지 속 주민등록번호 뒷자리가 스크럽된다."""
    rec = _record("user rrn 900101-1234567 registered")
    ScrubFilter().filter(rec)
    out = rec.getMessage()
    assert "1234567" not in out


def test_scrub_filter_keeps_normal_message() -> None:
    """정상 메시지는 그대로 둔다(오탐 0)."""
    rec = _record("user logged in profile_id=%s count=%s", (123, 4))
    ScrubFilter().filter(rec)
    assert rec.getMessage() == "user logged in profile_id=123 count=4"


def test_scrub_filter_preserves_lazy_percent() -> None:
    """lazy % 병합 결과가 보존된다(§9)."""
    rec = _record("value=%s", ("plain",))
    ScrubFilter().filter(rec)
    assert rec.getMessage() == "value=plain"
