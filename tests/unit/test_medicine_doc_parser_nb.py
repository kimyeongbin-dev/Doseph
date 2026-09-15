"""Unit tests for NB_DOC_DATA / UD_DOC_DATA 카테고리 파싱 (P5-B).

docs-private/PLAN_DRUG_DB_INGEST.md §2 — 식약처 NB_DOC_DATA 의 ARTICLE.title 을 10 카테고리로
정규화해 dict 로 분류, "이상반응" 만 별도 list 로 분리.
"""

from app.services.medicine_doc_parser import (
    normalize_nb_article_title,
    parse_nb_categories,
    parse_ud_plaintext,
)

# ── normalize_nb_article_title ──────────────────────────────────────────────


def test_normalize_warning_with_number_prefix() -> None:
    assert normalize_nb_article_title("1. 경고") == "경고"


def test_normalize_warning_no_space() -> None:
    assert normalize_nb_article_title("1.경고") == "경고"


def test_normalize_contraindication() -> None:
    assert normalize_nb_article_title("2. 다음 환자에는 투여하지 말 것.") == "금기"


def test_normalize_cautious_use() -> None:
    assert normalize_nb_article_title("3.다음 환자에는 신중히 투여할 것.") == "신중 투여"


def test_normalize_adverse_reaction_returns_special_marker() -> None:
    """이상반응 카테고리는 정규화 결과 '이상반응' — precautions 에서 분리되어야 함."""
    assert normalize_nb_article_title("4. 이상반응") == "이상반응"


def test_normalize_general_precaution() -> None:
    assert normalize_nb_article_title("5. 일반적 주의") == "일반적 주의"


def test_normalize_pregnancy() -> None:
    assert normalize_nb_article_title("6. 임부에 대한 투여") == "임부에 대한 투여"


def test_normalize_pediatric() -> None:
    assert normalize_nb_article_title("7. 소아에 대한 투여") == "소아에 대한 투여"


def test_normalize_elderly() -> None:
    assert normalize_nb_article_title("8.고령자에 대한 투여") == "고령자에 대한 투여"


def test_normalize_overdose() -> None:
    assert normalize_nb_article_title("9. 과량투여시의 처치") == "과량투여시의 처치"


def test_normalize_application_caution() -> None:
    assert normalize_nb_article_title("10. 적용상의 주의") == "적용상의 주의"


def test_normalize_unknown_returns_none() -> None:
    assert normalize_nb_article_title("11. 알 수 없는 분류") is None


def test_normalize_empty_returns_none() -> None:
    assert normalize_nb_article_title("") is None
    assert normalize_nb_article_title(None) is None


# ── parse_nb_categories ─────────────────────────────────────────────────────

_NB_SAMPLE = """<DOC title="사용상의주의사항" type="NB">
  <SECTION title="">
    <ARTICLE title="1. 경고">
      <PARAGRAPH><![CDATA[앰플 절단시 유리파편 주의.]]></PARAGRAPH>
      <PARAGRAPH><![CDATA[치아민 결핍 가능성.]]></PARAGRAPH>
    </ARTICLE>
    <ARTICLE title="2. 다음 환자에는 투여하지 말 것.">
      <PARAGRAPH><![CDATA[저장성 탈수증 환자]]></PARAGRAPH>
      <PARAGRAPH><![CDATA[고혈당 환자]]></PARAGRAPH>
    </ARTICLE>
    <ARTICLE title="3. 다음 환자에는 신중히 투여할 것.">
      <PARAGRAPH><![CDATA[당뇨환자]]></PARAGRAPH>
    </ARTICLE>
    <ARTICLE title="4. 이상반응">
      <PARAGRAPH><![CDATA[저칼륨혈증]]></PARAGRAPH>
      <PARAGRAPH><![CDATA[탈수증]]></PARAGRAPH>
      <PARAGRAPH><![CDATA[열, 정맥염]]></PARAGRAPH>
    </ARTICLE>
    <ARTICLE title="5. 일반적 주의">
      <PARAGRAPH><![CDATA[혈청 전해질 검사를 한다.]]></PARAGRAPH>
    </ARTICLE>
    <ARTICLE title="6. 임부에 대한 투여">
      <PARAGRAPH><![CDATA[임신 중 안전성 미확립.]]></PARAGRAPH>
    </ARTICLE>
  </SECTION>
</DOC>"""


def test_parse_nb_categories_returns_dict_and_side_effects_tuple() -> None:
    precautions, side_effects = parse_nb_categories(_NB_SAMPLE)
    assert isinstance(precautions, dict)
    assert isinstance(side_effects, list)


def test_parse_nb_categories_classifies_each_article() -> None:
    precautions, _ = parse_nb_categories(_NB_SAMPLE)
    assert "경고" in precautions
    assert "금기" in precautions
    assert "신중 투여" in precautions
    assert "일반적 주의" in precautions
    assert "임부에 대한 투여" in precautions


def test_parse_nb_categories_separates_adverse_reaction() -> None:
    """이상반응 ARTICLE 은 precautions 에 들어가면 안 되고 side_effects 에만."""
    precautions, side_effects = parse_nb_categories(_NB_SAMPLE)
    assert "이상반응" not in precautions
    assert side_effects == ["저칼륨혈증", "탈수증", "열, 정맥염"]


def test_parse_nb_categories_paragraphs_per_category() -> None:
    precautions, _ = parse_nb_categories(_NB_SAMPLE)
    assert precautions["경고"] == [
        "앰플 절단시 유리파편 주의.",
        "치아민 결핍 가능성.",
    ]
    assert precautions["금기"] == ["저장성 탈수증 환자", "고혈당 환자"]


def test_parse_nb_categories_empty_input() -> None:
    assert parse_nb_categories(None) == ({}, [])
    assert parse_nb_categories("") == ({}, [])
    assert parse_nb_categories("   ") == ({}, [])


def test_parse_nb_categories_malformed_xml() -> None:
    """파싱 실패 시 raise 가 아니라 빈 결과 반환 (parse_doc_articles 와 동일 정책)."""
    assert parse_nb_categories("<not valid xml") == ({}, [])


def test_parse_nb_categories_unknown_article_skipped() -> None:
    """매칭 실패한 ARTICLE 은 결과에 포함 안 됨 (로그만)."""
    xml = """<DOC><SECTION>
      <ARTICLE title="99. 처음 보는 카테고리">
        <PARAGRAPH>무언가</PARAGRAPH>
      </ARTICLE>
      <ARTICLE title="1. 경고">
        <PARAGRAPH>경고 내용</PARAGRAPH>
      </ARTICLE>
    </SECTION></DOC>"""
    precautions, side_effects = parse_nb_categories(xml)
    assert precautions == {"경고": ["경고 내용"]}
    assert side_effects == []


# ── parse_ud_plaintext ─────────────────────────────────────────────────────


def test_parse_ud_plaintext_joins_paragraphs() -> None:
    xml = """<DOC><SECTION><ARTICLE title="">
      <PARAGRAPH><![CDATA[성인: 1회 20-500 mL 정맥주사한다.]]></PARAGRAPH>
      <PARAGRAPH><![CDATA[연령에 따라 적절히 증감한다.]]></PARAGRAPH>
    </ARTICLE></SECTION></DOC>"""
    result = parse_ud_plaintext(xml)
    assert "성인: 1회 20-500 mL 정맥주사한다." in result
    assert "연령에 따라 적절히 증감한다." in result


def test_parse_ud_plaintext_empty_input() -> None:
    assert parse_ud_plaintext(None) == ""
    assert parse_ud_plaintext("") == ""
