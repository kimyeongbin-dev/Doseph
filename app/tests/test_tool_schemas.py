"""Tool schema contract tests (옵션 C 1단계).

Router LLM 의 ``tools`` 파라미터에 그대로 들어가는 정적 dict 들이 OpenAI
function-calling 규약과 본 프로젝트의 dispatch 계약을 동시에 만족하는지
검증한다. 본 모듈은 OpenAI 호출을 하지 않고 schema 모양만 본다.

옵션 C 의 핵심 변화: ``search_medicine_knowledge_base`` 가 추가돼 RAG 검색이
Router LLM 의 도구 선택 결과로 흡수된다. 의학 도메인 의도 분류는
IntentClassifier 가 아닌 Router 의 tool 선택으로 결정된다.
"""

from app.services.tools.schemas import (
  HOSPITAL_KEYWORD_TOOL,
  HOSPITAL_LOCATION_TOOL,
  MEDICINE_KNOWLEDGE_TOOL,
  TOOL_SCHEMAS,
)


class TestMedicineKnowledgeTool:
  def test_function_name(self) -> None:
    assert MEDICINE_KNOWLEDGE_TOOL["function"]["name"] == "search_medicine_knowledge_base"

  def test_type_is_function(self) -> None:
    assert MEDICINE_KNOWLEDGE_TOOL["type"] == "function"

  def test_query_is_required_string(self) -> None:
    params = MEDICINE_KNOWLEDGE_TOOL["function"]["parameters"]
    assert params["type"] == "object"
    assert "query" in params["properties"]
    assert params["properties"]["query"]["type"] == "string"
    assert params["required"] == ["query"]

  def test_description_mentions_medical_domain(self) -> None:
    description = MEDICINE_KNOWLEDGE_TOOL["function"]["description"]
    # description 은 Router LLM 의 의도 분류 근거로 동작하므로
    # '의학' 도메인 키워드가 반드시 포함돼야 한다.
    assert "의학" in description or "약" in description


class TestToolSchemasRegistry:
  def test_registry_includes_all_three_tools(self) -> None:
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert "search_hospitals_by_location" in names
    assert "search_hospitals_by_keyword" in names
    assert "search_medicine_knowledge_base" in names

  def test_registry_has_no_duplicates(self) -> None:
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert len(names) == len(set(names))

  def test_existing_tool_schemas_preserved(self) -> None:
    # 위치/키워드 tool 은 옵션 C 에서 변경되지 않아야 한다.
    assert HOSPITAL_LOCATION_TOOL["function"]["name"] == "search_hospitals_by_location"
    assert HOSPITAL_KEYWORD_TOOL["function"]["name"] == "search_hospitals_by_keyword"
