"""Log-safety utilities — sensitive-data masking + scrub filter (B5).

로그(stdout/파일)로 PII·시크릿이 새지 않게 하는 **심층 방어(defense-in-depth)**:
- **1차(명시적)**: 호출자가 ``mask_*`` 로 값을 마스킹해 로깅(정밀·오탐 없음).
- **2차(안전망)**: ``ScrubFilter`` 를 핸들러에 부착 — **오탐 낮은 고신뢰 패턴만**
  (JWT / ``Bearer <tok>`` / 주민등록번호) 최종 메시지에서 스크럽. 개발자가 1차를
  누락해도 잡아냄. 전화·이메일은 오탐 위험이 커 스크럽 대상에서 제외(명시적 마스킹만).

프레임워크 비의존 순수 로직(logging·re 만) → 단위테스트 용이·결합도↓.
브라우저엔 애초에 서버 로그가 전달되지 않음(§9) — 이 유틸은 서버측 로그 산출물
(app.log·stdout·수집기) 보호용.
"""

import logging
import re

_MASK = "***"

# ── 마스킹 패턴 (컴파일 1회) ───────────────────────────────────────────
_PHONE_RE = re.compile(r"(\d{2,3})[- ]?(\d{3,4})[- ]?(\d{4})")
_RRN_RE = re.compile(r"(\d{6})-?(\d{7})")
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")

# ── 스크럽 패턴 (고신뢰·오탐 낮음) ─────────────────────────────────────
_JWT_SCRUB = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_BEARER_SCRUB = re.compile(r"(?i)(Bearer)\s+[A-Za-z0-9\-._~+/]+=*")
_RRN_SCRUB = re.compile(r"\b(\d{6})-?\d{7}\b")


# ── 명시적 마스킹 함수 (1차 방어) ──────────────────────────────────────
# 흐름: 호출자가 로깅 직전 값을 마스킹 -> 마스킹된 문자열만 로그 메시지에 사용
def mask_token(value: str) -> str:
    """토큰/시크릿 값을 통째로 마스킹(원문 흔적 제거).

    Args:
        value: 원본 토큰/시크릿.

    Returns:
        빈 값이면 그대로, 아니면 ``***``.
    """
    return _MASK if value else value


def mask_authorization(value: str) -> str:
    """Authorization 헤더 값에서 스킴만 남기고 자격증명을 마스킹.

    Args:
        value: 예) ``Bearer eyJ...``.

    Returns:
        예) ``Bearer ***`` (스킴 없으면 ``***``).
    """
    parts = value.split(None, 1)
    if len(parts) == 2:
        return f"{parts[0]} {_MASK}"
    return _MASK


def mask_phone(value: str) -> str:
    """문자열 속 전화번호의 가운데 자리를 마스킹.

    Args:
        value: 전화번호를 포함할 수 있는 문자열.

    Returns:
        가운데 그룹이 ``****`` 로 치환된 문자열.
    """
    return _PHONE_RE.sub(lambda m: f"{m.group(1)}-****-{m.group(3)}", value)


def mask_rrn(value: str) -> str:
    """문자열 속 주민등록번호 뒷자리(7자리)를 마스킹.

    Args:
        value: 주민등록번호를 포함할 수 있는 문자열.

    Returns:
        뒷자리가 ``*******`` 로 치환된 문자열.
    """
    return _RRN_RE.sub(lambda m: f"{m.group(1)}-{'*' * 7}", value)


def mask_email(value: str) -> str:
    """문자열 속 이메일을 로컬파트 첫 글자 + 도메인만 남기고 마스킹.

    Args:
        value: 이메일을 포함할 수 있는 문자열.

    Returns:
        예) ``a***@doseph.com``.
    """
    return _EMAIL_RE.sub(lambda m: f"{m.group(1)}***{m.group(2)}", value)


# ── 스크럽 필터 (2차 안전망, 핸들러 부착) ──────────────────────────────
# 흐름: 최종 메시지 확보 -> JWT/Bearer/주민번호 고신뢰 패턴만 스크럽
#       -> record 재기록(모든 핸들러 공통). TruncateFilter 뒤에 부착.
class ScrubFilter(logging.Filter):
    """최종 로그 메시지에서 고신뢰 민감패턴을 스크럽하는 안전망 필터.

    명시적 마스킹(1차)을 누락해도 JWT·Bearer 토큰·주민등록번호는 로그로 새지
    않게 막는다. 오탐(정상 데이터 훼손)을 피하려 **패턴을 좁게** 유지한다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        scrubbed = _JWT_SCRUB.sub(_MASK, message)
        scrubbed = _BEARER_SCRUB.sub(lambda m: f"{m.group(1)} {_MASK}", scrubbed)
        scrubbed = _RRN_SCRUB.sub(lambda m: f"{m.group(1)}-{'*' * 7}", scrubbed)
        record.msg = scrubbed
        record.args = None
        return True
