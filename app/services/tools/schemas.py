"""OpenAI ``tools`` 파라미터에 그대로 넣을 수 있는 함수 선언.

Router LLM 은 다섯 함수를 인지한다:
- ``search_hospitals_by_location`` — 사용자 GPS 좌표가 필요한 위치 검색.
- ``search_hospitals_by_keyword`` — 지명/지역명/랜드마크 등 자유 키워드 검색.
- ``search_medicine_knowledge_base`` — 약 정보/부작용/복용법/상호작용 등
  의학 지식 검색 (RAG retrieval). 의학 도메인 질문이면 본 tool 호출 강제.
- ``check_user_medications_recall`` — 사용자 복용약의 식약처 회수/판매중지
  조회 (회수/리콜/ban/판매금지 등 동의어 풀 강화).
- ``check_manufacturer_recalls`` — 제조사 단위 회수 이력 조회.

병렬 호출 정책:
    호출 측에서 ``parallel_tool_calls=True`` + ``tool_choice="auto"`` 로
    호출하면 LLM 이 여러 함수를 한 응답에 묶어 호출할 수 있다. message_service
    는 모든 결과를 ``asyncio.gather`` 로 모아 2nd LLM 호출에 전달한다.

description 은 한국어:
    LLM 의 의도 분류 정확도를 위해 사용자가 보낼 한국어 표현과 가까운
    용어로 작성한다 (예: "주변 약국", "근처 병원", "강남역 약국").
"""

from typing import Any

HOSPITAL_LOCATION_TOOL: dict[str, Any] = {
  "type": "function",
  "function": {
    "name": "search_hospitals_by_location",
    "description": (
      "사용자 GPS 좌표 주변에서 약국 또는 병원을 검색한다. "
      "사용자가 '내 주변', '근처', '가까운' 같은 표현으로 위치 기반 추천을 "
      "요청할 때 사용한다. 좌표는 백엔드가 별도로 수집하므로 인자에는 포함하지 "
      "않는다."
    ),
    "parameters": {
      "type": "object",
      "properties": {
        "category": {
          "type": "string",
          "enum": ["약국", "병원"],
          "description": "검색 대상 카테고리. 약국 또는 병원.",
        },
        "radius_m": {
          "type": "integer",
          "description": "검색 반경 (m). 기본 1000m.",
          "default": 1000,
        },
      },
      "required": ["category"],
    },
  },
}

HOSPITAL_KEYWORD_TOOL: dict[str, Any] = {
  "type": "function",
  "function": {
    "name": "search_hospitals_by_keyword",
    "description": (
      "지명, 지역명, 랜드마크 등 자유 키워드로 약국/병원을 검색한다. "
      "사용자가 '강남역 약국', '역삼동 병원', '서울대병원' 처럼 "
      "특정 위치 키워드를 명시했을 때 사용한다."
    ),
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "검색 키워드. 예: '강남역 약국', '서울대병원'",
        },
      },
      "required": ["query"],
    },
  },
}

MEDICINE_KNOWLEDGE_TOOL: dict[str, Any] = {
  "type": "function",
  "function": {
    "name": "search_medicine_knowledge_base",
    "description": (
      "약 정보, 부작용, 복용법, 효능, 성분, 상호작용 등 의학 도메인 지식 질문에 사용한다. "
      "사용자 질문이 의학/약학 도메인이면 반드시 호출. 일반 잡담·인사·정치·날씨 등 "
      "도메인 외 질문에는 호출하지 않는다. 인자 query 는 대화 이력의 대명사·생략된 "
      "주어·지시어를 풀어 self-contained 한 한 문장으로 작성한다."
    ),
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": (
            "검색 질의. history 의 대명사·생략된 주어를 풀어 한 문장으로 작성. "
            "예: '타이레놀의 부작용', '오메가3와 와파린의 상호작용'"
          ),
        },
      },
      "required": ["query"],
    },
  },
}

# ── 식약처 회수·판매중지 툴 (Phase 7, §15.3 동의어 풀 강화) ──────────
# Router LLM 의 매칭 정확도를 위해 description 에 회수 도메인 동의어를
# 명시한다. OpenAI Function Calling 공식 best practice — 동의어 10~15개
# 명시 시 오타·영한혼용·줄임말 견고성이 비약적으로 상승.

CHECK_USER_MEDICATIONS_RECALL_TOOL: dict[str, Any] = {
  "type": "function",
  "function": {
    "name": "check_user_medications_recall",
    "description": (
      "사용자가 마이페이지에 등록한 복용 중 약품들 중에서 "
      "식약처에서 회수, 판매중지, 판매중단, 판매금지, 리콜, "
      "ban, 회수당한, 회수처리, 회수조치, 회수명령, 판중지, "
      "판매정지, 시판중지된 약품이 있는지 확인합니다. "
      "사용자의 질문에 회수/판매중지/리콜/ban/금지/정지 등 "
      "관련 키워드가 변형되거나 오타가 있어도 본 함수를 호출하세요. "
      "인자는 없으며 백엔드가 profile_id 를 자동 주입합니다."
    ),
    "parameters": {"type": "object", "properties": {}},
  },
}

CHECK_MANUFACTURER_RECALLS_TOOL: dict[str, Any] = {
  "type": "function",
  "function": {
    "name": "check_manufacturer_recalls",
    "description": (
      "사용자가 복용 중인 약의 제조사(제약회사)에서 발생한 "
      "회수·판매중지·리콜·ban·판매금지·시판중지 이력을 조회합니다. "
      "'내 약 만든 회사', '동국제약 회수', '제조사가 회수당한 거', "
      "'어느 회사 회수' 같은 제조사 단위 질의에 사용합니다. "
      "오타·띄어쓰기 변형·영한혼용이 있어도 본 함수를 호출하세요."
    ),
    "parameters": {
      "type": "object",
      "properties": {
        "manufacturer": {
          "type": "string",
          "description": (
            "선택: 특정 제조사명. 비우면 사용자 복용약 제조사 전체를 "
            "자동 조회. 사용자가 '동국제약', '한미약품' 등 명시했을 때만 채움."
          ),
        },
      },
    },
  },
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
  HOSPITAL_LOCATION_TOOL,
  HOSPITAL_KEYWORD_TOOL,
  MEDICINE_KNOWLEDGE_TOOL,
  CHECK_USER_MEDICATIONS_RECALL_TOOL,
  CHECK_MANUFACTURER_RECALLS_TOOL,
]
