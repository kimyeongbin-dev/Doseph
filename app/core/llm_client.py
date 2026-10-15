"""LLM 클라이언트 **생성** 정본 — 제공자·주소가 바뀌면 이 파일만 고친다.

왜 생성만 모으나 (2026-10-16, v2.0 재배포 PLAN S1)
------------------------------------------------
클라이언트를 만드는 자리가 4곳(``query_rewriter`` · ``openai_embedding`` ·
``ai_worker.core.openai_client`` · ``lifestyle.jobs``)에 흩어져 있었다.
제공자를 바꾸려면 4곳을 같은 모양으로 고쳐야 했고, 하나라도 빠지면 그 경로만
옛 제공자로 조용히 남는다.

🔑 **싱글톤은 각 모듈에 그대로 둔다.** 테스트가 모듈별 ``_initialised`` 와
``config`` 를 직접 바꿔 끼워 키 분기를 **실제로** 돌리고 있어서, 싱글톤까지 합치면
그 패치 지점이 한꺼번에 무너진다. 여기는 «만드는 한 줄» 만 맡는다.
"""

from openai import AsyncOpenAI


# ── LLM 클라이언트 생성 ──────────────────────────────────────────────
# 흐름: API 키 -> AsyncOpenAI 인스턴스
# 키 유무 판단과 싱글톤 보관은 호출자 몫이다(없을 때 None 이냐 예외냐가 경로마다 다르다).
def build_llm_client(api_key: str) -> AsyncOpenAI:
  """API 키로 LLM 비동기 클라이언트를 만든다."""
  return AsyncOpenAI(api_key=api_key)
