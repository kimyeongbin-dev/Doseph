"""제조사명 정규화 함수 테스트 (§14.5 발견 #2).

식약처 회수 API 의 `entrpsName` 과 의약품 허가 API 의 `ENTP_NAME`
표기가 일치하지 않는 경우가 많아 Q2 (제조사별 회수) 매칭이 깨짐.
정규화 함수가 다음 패턴을 처리해야 함:

- `(주)` / `(株)` 위치 변동 (앞·뒤 / 중간 / 미존재)
- `주식회사` 한글 표기 → 동일 정규형
- 공백·NBSP·전각 공백 정규화
- 빈 문자열·None 안전 처리

이 테스트는 §14.5.3 의 실제 시드 표기 5종을 직접 케이스로 사용해
운영 정확성을 보장한다.
"""

import pytest

from app.utils.company_name_normalizer import normalize_company_name


class TestParenJusik:
  """(주) / (株) / 주식회사 표기 제거."""

  def test_trailing_paren_jusik_removed(self) -> None:
    """`동국제약(주)` → `동국제약`."""
    assert normalize_company_name("동국제약(주)") == "동국제약"

  def test_leading_paren_jusik_removed(self) -> None:
    """`(주)한독` → `한독`."""
    assert normalize_company_name("(주)한독") == "한독"

  def test_long_company_with_trailing_paren_jusik(self) -> None:
    """`제이더블유중외제약(주)` → `제이더블유중외제약`."""
    assert normalize_company_name("제이더블유중외제약(주)") == "제이더블유중외제약"

  def test_hanja_paren_jusik_removed(self) -> None:
    """`동국제약(株)` → `동국제약` (한자 株 도 처리)."""
    assert normalize_company_name("동국제약(株)") == "동국제약"

  def test_jusik_word_removed(self) -> None:
    """`주식회사 동국제약` / `동국제약 주식회사` → `동국제약`."""
    assert normalize_company_name("주식회사 동국제약") == "동국제약"
    assert normalize_company_name("동국제약 주식회사") == "동국제약"

  def test_no_paren_jusik_unchanged(self) -> None:
    """`한미약품` 같이 이미 정규형은 그대로."""
    assert normalize_company_name("한미약품") == "한미약품"


class TestWhitespace:
  """공백 정규화."""

  def test_leading_trailing_whitespace_stripped(self) -> None:
    """선행·후행 공백 제거."""
    assert normalize_company_name("  동국제약(주)  ") == "동국제약"

  def test_internal_multi_space_collapsed(self) -> None:
    """내부 다중 공백을 단일 공백으로 압축 (제거가 아님)."""
    assert normalize_company_name("주식회사   동국제약") == "동국제약"

  def test_nbsp_treated_as_space(self) -> None:
    """NBSP (U+00A0) 는 일반 공백으로 정규화 후 처리."""
    assert normalize_company_name(" 동국제약(주) ") == "동국제약"  # noqa: RUF001


class TestEdgeCases:
  """경계 케이스 안전 처리."""

  def test_empty_string(self) -> None:
    """빈 문자열은 빈 문자열로 반환."""
    assert normalize_company_name("") == ""

  def test_whitespace_only(self) -> None:
    """공백만 있는 문자열은 빈 문자열로 반환."""
    assert normalize_company_name("   ") == ""

  def test_none_returns_empty_string(self) -> None:
    """None 입력은 빈 문자열로 반환 (NULL safety)."""
    assert normalize_company_name(None) == ""  # type: ignore[arg-type]


class TestSeedManufacturers:
  """§14.5.3 시드 제조사 5종 — 실제 회수 데이터 표기 검증."""

  @pytest.mark.parametrize(
    ("raw", "expected"),
    [
      ("동국제약(주)", "동국제약"),
      ("동아제약(주)", "동아제약"),
      ("광동제약(주)", "광동제약"),
      ("한림제약(주)", "한림제약"),
      ("삼성제약(주)", "삼성제약"),
      # 기타 §14.5.1 표기
      ("(주)화이트생명과학", "화이트생명과학"),
      ("(주)한독", "한독"),
      ("부광약품(주)", "부광약품"),
      ("제이더블유중외제약(주)", "제이더블유중외제약"),
      ("(주)종근당", "종근당"),
      ("(주)팜젠사이언스", "팜젠사이언스"),
      ("국제약품(주)", "국제약품"),
      ("진양제약(주)", "진양제약"),
    ],
  )
  def test_seed_manufacturers_normalized(self, raw: str, expected: str) -> None:
    """§14.5 시드의 모든 제조사 표기가 정규형으로 매핑되어야 한다."""
    assert normalize_company_name(raw) == expected

  def test_normalize_idempotent(self) -> None:
    """이미 정규화된 값을 다시 넣어도 결과가 같아야 한다 (idempotent)."""
    once = normalize_company_name("동국제약(주)")
    twice = normalize_company_name(once)
    assert once == twice == "동국제약"
