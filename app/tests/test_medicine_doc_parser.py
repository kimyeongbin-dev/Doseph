# ruff: noqa: RUF001, E501
# RUF001: 공공 API 실제 응답의 TILDE OPERATOR 등 특수문자를 그대로 샘플에 포함해야 파서 계약이 검증됨
# E501: 한글 포함 XML 샘플 라인은 ruff 폭 계산상 길게 잡히지만 실제 가독성 이슈 아님
"""Dtl06 문서 XML 파서 계약 테스트.

app/services/medicine_doc_parser.py의 세 함수를 검증한다:
- parse_doc_articles(xml) -> list[Article]
- flatten_doc_plaintext(xml) -> str
- classify_article_section(title) -> MedicineChunkSection

현실에서 들어오는 EE/UD/NB_DOC_DATA 샘플 구조 기반으로 작성하되,
DB/네트워크 의존 없이 순수 함수 단위로 테스트한다.
"""

from app.models.medicine_chunk import MedicineChunkSection
from app.services.medicine_doc_parser import (
  Article,
  classify_article_section,
  flatten_doc_plaintext,
  parse_doc_articles,
)

# ── 실제 Dtl06 응답 구조 기반 샘플 XML ───────────────────────────────

EE_DOC_SAMPLE = """<DOC title="효능효과" type="EE">
  <SECTION title="">
    <ARTICLE title="1. 고칼륨혈증, 순환허탈, 저혈당시의 에너지 보급" />
    <ARTICLE title="2. 심질환(G,I,K요법) 그 외 수분, 에너지 보급" />
    <ARTICLE title="3. 약물ㆍ독물 중독" />
  </SECTION>
</DOC>"""

UD_DOC_SAMPLE = """<DOC title="용법용량" type="UD">
  <SECTION title="">
    <ARTICLE title="">
      <PARAGRAPH tagName="p" textIndent="" marginLeft=""><![CDATA[○ 성인 : 1회 20∼500 mL 정맥주사한다.]]></PARAGRAPH>
      <PARAGRAPH tagName="p" textIndent="" marginLeft=""><![CDATA[○ 점적정맥주사 속도는 포도당으로서 시간당 0.5 g/kg 이하로 한다.]]></PARAGRAPH>
    </ARTICLE>
  </SECTION>
</DOC>"""

NB_DOC_SAMPLE = """<DOC title="사용상의주의사항" type="NB">
  <SECTION title="">
    <ARTICLE title="1. 경고">
      <PARAGRAPH tagName="p"><![CDATA[1) 앰플주사제는 용기 절단시 유리파편이 혼입될 수 있다.]]></PARAGRAPH>
    </ARTICLE>
    <ARTICLE title="2. 다음 환자에는 투여하지 말 것.">
      <PARAGRAPH tagName="p"><![CDATA[1) 저장성 탈수증 환자]]></PARAGRAPH>
      <PARAGRAPH tagName="p"><![CDATA[2) 수분과다상태 환자]]></PARAGRAPH>
    </ARTICLE>
    <ARTICLE title="3. 다음 환자에는 신중히 투여할 것.">
      <PARAGRAPH tagName="p"><![CDATA[1) 신부전 환자]]></PARAGRAPH>
    </ARTICLE>
  </SECTION>
</DOC>"""


class TestParseDocArticlesEfficacy:
  """EE_DOC_DATA (title만 있고 PARAGRAPH 없는 구조) 파싱."""

  def test_returns_three_articles(self) -> None:
    articles = parse_doc_articles(EE_DOC_SAMPLE)
    assert len(articles) == 3

  def test_each_article_has_title_only(self) -> None:
    articles = parse_doc_articles(EE_DOC_SAMPLE)
    assert articles[0].title == "1. 고칼륨혈증, 순환허탈, 저혈당시의 에너지 보급"
    assert articles[0].body == ""

  def test_third_article_title(self) -> None:
    articles = parse_doc_articles(EE_DOC_SAMPLE)
    assert articles[2].title == "3. 약물ㆍ독물 중독"


class TestParseDocArticlesUsage:
  """UD_DOC_DATA (title 없고 PARAGRAPH 여러 개)."""

  def test_returns_single_article(self) -> None:
    articles = parse_doc_articles(UD_DOC_SAMPLE)
    assert len(articles) == 1

  def test_article_body_joins_paragraphs(self) -> None:
    articles = parse_doc_articles(UD_DOC_SAMPLE)
    body = articles[0].body
    assert "○ 성인 : 1회 20∼500 mL 정맥주사한다." in body
    assert "○ 점적정맥주사 속도는 포도당으로서 시간당 0.5 g/kg 이하로 한다." in body

  def test_article_title_empty_when_source_empty(self) -> None:
    articles = parse_doc_articles(UD_DOC_SAMPLE)
    assert articles[0].title == ""


class TestParseDocArticlesPrecaution:
  """NB_DOC_DATA (복수 ARTICLE + 섹션성 title)."""

  def test_returns_three_articles(self) -> None:
    articles = parse_doc_articles(NB_DOC_SAMPLE)
    assert len(articles) == 3

  def test_warning_article(self) -> None:
    articles = parse_doc_articles(NB_DOC_SAMPLE)
    warning = articles[0]
    assert warning.title == "1. 경고"
    assert "앰플주사제는 용기 절단시 유리파편이 혼입될 수 있다." in warning.body

  def test_contraindication_body_has_all_paragraphs(self) -> None:
    articles = parse_doc_articles(NB_DOC_SAMPLE)
    contra = articles[1]
    assert contra.title == "2. 다음 환자에는 투여하지 말 것."
    assert "저장성 탈수증 환자" in contra.body
    assert "수분과다상태 환자" in contra.body


class TestParseDocArticlesEdgeCases:
  """빈 입력/None/잘못된 XML 안전 처리."""

  def test_none_returns_empty_list(self) -> None:
    assert parse_doc_articles(None) == []

  def test_empty_string_returns_empty_list(self) -> None:
    assert parse_doc_articles("") == []

  def test_whitespace_only_returns_empty_list(self) -> None:
    assert parse_doc_articles("   \n\t  ") == []

  def test_malformed_xml_returns_empty_list(self) -> None:
    assert parse_doc_articles("<DOC><unclosed>") == []

  def test_no_article_returns_empty_list(self) -> None:
    xml = '<DOC title="" type="EE"><SECTION title=""></SECTION></DOC>'
    assert parse_doc_articles(xml) == []


class TestFlattenDocPlaintext:
  """XML → 단일 평문 (UI/efficacy 컬럼 저장용)."""

  def test_efficacy_flattens_titles(self) -> None:
    text = flatten_doc_plaintext(EE_DOC_SAMPLE)
    assert "1. 고칼륨혈증, 순환허탈, 저혈당시의 에너지 보급" in text
    assert "2. 심질환(G,I,K요법) 그 외 수분, 에너지 보급" in text
    assert "3. 약물ㆍ독물 중독" in text

  def test_usage_flattens_paragraphs(self) -> None:
    text = flatten_doc_plaintext(UD_DOC_SAMPLE)
    assert "○ 성인 : 1회 20∼500 mL 정맥주사한다." in text
    assert "시간당 0.5 g/kg 이하" in text

  def test_no_tags_remain(self) -> None:
    text = flatten_doc_plaintext(NB_DOC_SAMPLE)
    assert "<" not in text
    assert ">" not in text
    assert "PARAGRAPH" not in text
    assert "CDATA" not in text

  def test_none_returns_empty_string(self) -> None:
    assert flatten_doc_plaintext(None) == ""

  def test_empty_string_returns_empty_string(self) -> None:
    assert flatten_doc_plaintext("") == ""

  def test_malformed_xml_returns_empty_string(self) -> None:
    assert flatten_doc_plaintext("<DOC><unclosed>") == ""


class TestClassifyArticleSection:
  """ARTICLE title → MedicineChunkSection (v2 6섹션) 키워드 매칭."""

  def test_warning_maps_to_special_event(self) -> None:
    assert classify_article_section("1. 경고") == MedicineChunkSection.SPECIAL_EVENT

  def test_contraindication_maps_to_drug_interaction(self) -> None:
    assert classify_article_section("2. 다음 환자에는 투여하지 말 것") == MedicineChunkSection.DRUG_INTERACTION

  def test_contraindication_keyword_maps_to_drug_interaction(self) -> None:
    assert classify_article_section("병용금기") == MedicineChunkSection.DRUG_INTERACTION

  def test_caution_maps_to_drug_interaction(self) -> None:
    assert classify_article_section("3. 다음 환자에는 신중히 투여할 것") == MedicineChunkSection.DRUG_INTERACTION

  def test_adverse_reaction_by_formal(self) -> None:
    assert classify_article_section("4. 이상반응") == MedicineChunkSection.ADVERSE_REACTION

  def test_adverse_reaction_by_common(self) -> None:
    assert classify_article_section("부작용") == MedicineChunkSection.ADVERSE_REACTION

  def test_pregnancy_maps_to_special_event(self) -> None:
    assert classify_article_section("5. 임부 및 수유부에 대한 투여") == MedicineChunkSection.SPECIAL_EVENT

  def test_pediatric_maps_to_special_event(self) -> None:
    assert classify_article_section("6. 소아에 대한 투여") == MedicineChunkSection.SPECIAL_EVENT

  def test_elderly_maps_to_special_event(self) -> None:
    assert classify_article_section("7. 고령자에 대한 투여") == MedicineChunkSection.SPECIAL_EVENT

  def test_overdose_maps_to_adverse_reaction(self) -> None:
    assert classify_article_section("8. 과량투여시의 처치") == MedicineChunkSection.ADVERSE_REACTION

  def test_alcohol_maps_to_lifestyle_interaction(self) -> None:
    assert classify_article_section("음주 시 주의") == MedicineChunkSection.LIFESTYLE_INTERACTION

  def test_driving_maps_to_lifestyle_interaction(self) -> None:
    assert classify_article_section("운전·기계조작") == MedicineChunkSection.LIFESTYLE_INTERACTION

  def test_unknown_falls_back_to_intake_guide(self) -> None:
    assert classify_article_section("일반적 주의") == MedicineChunkSection.INTAKE_GUIDE

  def test_empty_title_falls_back_to_intake_guide(self) -> None:
    assert classify_article_section("") == MedicineChunkSection.INTAKE_GUIDE


class TestArticleDataclass:
  """Article 레코드 구조 계약."""

  def test_article_has_title_and_body(self) -> None:
    article = Article(title="제목", body="본문")
    assert article.title == "제목"
    assert article.body == "본문"
