# RAG 4단 파이프라인 구현 문서

> **PR**: `feature/rag-pipeline` (main `ef4a390` 기준 분기, 2026-05-02)
> **연관 문서**: `docs/RAG_FLOW.md` (데이터 흐름), `PLAN.md` (결정 매트릭스), `docs/MIGRATIONS_NORMALIZATION.md` (마이그 정상화 — 별도 PR)
> **작성**: 본 PR 의 8 commits 산출물 정리
> **목적**: 팀원이 본 PR 을 이해하고 다음 PR 작성/머지/검증 시 참고

---

## 0. 한눈 요약

기존 Router LLM (4o) → tool_calls 흐름을 **RAG 4단 파이프라인** 으로 완전 재구축.

```
이전:  Router LLM (4o) → text 직답 OR tool_calls 병렬 → 2nd LLM
이후:  Step 0 (medical_context) → Step 1+2 (IntentClassifier 4o-mini)
        → direct_answer 즉시 응답 OR
        → fanout_queries → Step 3 (tool_calls 병렬) → Step 4 (RAG context inject + 2nd LLM)
```

| 변화 | 이전 | 이후 |
|---|---|---|
| 의도 분류 | Router LLM (gpt-4o) tool_choice | IntentClassifier (gpt-4o-mini) Structured Outputs |
| 사용자 컨텍스트 주입 | 없음 (Router LLM 이 history 만 봄) | medical_context (medication + Profile.health_survey) → IntentClassifier system prompt |
| 검색 쿼리 | LLM 이 1 개 query 생성 | fan-out cap=10 (음성응답 제외 + 임상 우선순위) |
| Hybrid retrieval | vector 0.7 + keyword 0.3 가중합 | RRF (Cormack 2009, k=60) — vector + tsvector BM25 |
| 임베딩 모델 | ko-sroberta (768d) | OpenAI text-embedding-3-large (3072d) |
| RAG context inject | tool 메시지로 LLM 에 전달 | system prompt 의 `[검색된 약품 정보]` 섹션 |
| recent history | 10 messages | 6 messages (compact 6-turn 정합) |
| retry | 없음 | 자체 decorator (Kakao API + OpenAI Embedding) |

---

## 1. 4단 파이프라인 구조

### Step 0 — Context Loader

| 입력 | `chat_session.profile_id` |
|---|---|
| 동작 | `medication` 테이블 + `Profile.health_survey` JSONField 조회 |
| 출력 | markdown `[사용자 의학 컨텍스트]` 섹션 |

```
- 복용 중인 약: 메트포민, 와파린, 오메가3, 타이레놀
- 기저질환: 당뇨, 고혈압, 심장질환, 신장질환
- 알레르기: 항생제, 소염제
- 흡연: 비흡연
- 음주: 비음주
```

→ 비어있으면 빈 문자열 반환 (섹션 자체 생략).

**구현**: `app/services/chat/medical_context.py:build_medical_context`

### Step 1+2 — IntentClassifier (4o-mini Structured Outputs)

| 입력 | history 6 messages + medical_context |
|---|---|
| LLM | gpt-4o-mini, `response_format=IntentClassification` |
| 출력 | `IntentClassification` Pydantic 객체 |

```python
class IntentClassification(BaseModel):
    intent: IntentType  # greeting / out_of_scope / domain_question / ambiguous
    direct_answer: str | None        # greeting/out_of_scope/ambiguous 시 채움
    fanout_queries: list[str] | None # domain_question 시 cap=10
    referent_resolution: dict[str, str] | None  # {"그거": "타이레놀"} 등
    filters: SearchFilters | None    # target_drug, target_section
```

#### 4가지 intent 분기

| intent | 다음 단계 | 예시 |
|---|---|---|
| `greeting` | direct_answer 즉시 응답, 종료 | "안녕" |
| `out_of_scope` | direct_answer 가이드, 종료 | "오늘 날씨 어때?" |
| `ambiguous` | direct_answer 명확화 질문, 종료 | "그거 부작용은?" (history 빈) |
| `domain_question` | fanout_queries 로 Step 3 진입 | "타이레놀 먹어도 돼?" |

#### fan-out 임상 우선순위 (cap=10)

```
1. 신규 약 vs 각 복용약 상호작용 (가장 위험)
2. 신규 약 vs 알레르기 (페니실린, 견과류 등)
3. 신규 약 vs 임신/수유 (해당 시만)
4. 신규 약 vs 각 기저질환 (당뇨, 고혈압 등)
5. 신규 약 vs 흡연/음주 (해당 시만 — 음성응답 제외)
6. 신규 약 자체 부작용/주의사항
```

→ 음성응답 (`is_smoking=False`) 은 query 만들지 않음 (system prompt 룰).

**구현**: `app/services/intent/classifier.py:classify_intent`, `app/services/chat/intent_orchestrator.py:classify_user_turn`

### Step 3 — Tool Dispatch (RAG retrieval 병렬)

| 입력 | `IntentClassification.fanout_queries` (N개) |
|---|---|
| 변환 | `search_medicine_knowledge_base` `ToolCall` × N |
| 실행 | `run_tool_calls_via_rq` → ai_worker.run_tool_calls_job (asyncio.gather 병렬) |
| 출력 | `{tool_call_id: {"chunks": [...]}}` |

각 tool_call 내부:
1. `encode_query` (OpenAI 3072d, retry 적용)
2. `HybridRetriever.retrieve` — pgvector cosine + tsvector BM25 1차 RRF (k=60)
3. medicine 단위 grouping + RRF score 합산

**구현**:
- `app/services/chat/fanout_tool_calls.py:fanout_to_tool_calls`
- `ai_worker/domains/tool_calling/jobs.py:run_tool_calls_job`
- `app/services/rag/retrievers/hybrid.py:HybridRetriever.retrieve`
- `app/services/rag/retrievers/rrf.py:rrf_intra_query`

### Step 4 — Prompt 조립 + 2nd LLM (4o)

#### system prompt 6 섹션 (RAG_FLOW.md §2.4 의 lost-in-middle 회피 순서)

```
1. persona ("Doseph" 약사 챗봇 + 해요체)
2. output rule (한국어 GFM, 코드블록 금지, 출처 인라인)
3. (의학 컨텍스트는 IntentClassifier 가 흡수 → 2nd LLM 에 별도 노출 X)
4. 세션 요약 (chat_sessions.summary, 옵션 D)
5. [명확화] (referent_resolution 있을 때만)
6. [검색된 약품 정보] ★ 가장 마지막 (lost-in-middle 회피)
   [약: 타이레놀] [drug_interaction]: 와파린과 병용 시 INR 상승...
   [약: 와파린] [drug_interaction]: 아세트아미노펜 병용 시 출혈 위험...
   ...
```

#### user/assistant messages

| role | content |
|---|---|
| system | (위 6 섹션 한 덩어리) |
| user (history -3) | 과거 turn raw query |
| assistant (history -3) | 과거 답변 |
| ... 6 messages 누적 ... | |
| **user (현재)** | **raw query 그대로** (canonical 도입 X) |

→ `_finalize_rag_turn` 이 OpenAI tool_call 페어링 안 함 (RAG 결과는 system inject, OpenAI tool 표준 흐름과 분리).

**구현**:
- `app/services/chat/rag_context_assembler.py:assemble_rag_section`
- `app/services/message_service.py:_compose_system_prompt`
- `app/services/message_service.py:_finalize_rag_turn`
- `ai_worker/domains/rag/jobs.py:generate_chat_response_job`

---

## 2. 디렉터리 변경 요약

### 신규 (10 모듈 + 1 __init__)

```
app/dtos/intent.py                              IntentClassification Pydantic
app/services/intent/__init__.py
app/services/intent/classifier.py               4o-mini Structured Outputs
app/services/chat/medical_context.py            DB 조회 + markdown 빌더
app/services/chat/intent_orchestrator.py        Step 0 + 1+2 통합
app/services/chat/fanout_tool_calls.py          IntentClassification → ToolCall list
app/services/chat/rag_context_assembler.py      tool_results → RAG section
app/services/tools/retry.py                     자체 retry decorator (~50라인)
app/services/tools/context_format.py            chunks → markdown N줄
app/services/rag/openai_embedding.py            text-embedding-3-large query 측
app/services/rag/retrievers/rrf.py              Cormack 2009 RRF (intra + cross)
```

### 삭제 (14 파일)

```
ai_worker/domains/tool_calling/router_llm.py    (Router LLM provider)
ai_worker/domains/rag/embedding_provider.py     (ko-sroberta SentenceTransformer)
app/services/tools/router.py                    (parse_router_response)
app/services/rag/providers/                     (rq_embedding + rq_llm)
app/tests/test_router_service.py
app/tests/test_recall_router_robustness.py
app/tests/test_ai_worker_router_provider.py
app/tests/test_ai_worker_tool_tasks.py
app/tests/test_message_routers_tools.py
app/tests/test_message_service_tool_branching.py
app/tests/test_tools_rq_adapters.py
app/tests/test_ai_worker_embedding_provider.py
app/tests/test_ai_worker_rag_dispatch.py
app/tests/test_ai_worker_rag_tasks.py
app/tests/test_rq_embedding_provider.py
app/tests/test_rq_rag_generator.py
```

### 주요 변경

| 파일 | 변경 |
|---|---|
| `app/services/message_service.py` | `ask_with_tools` 4단 파이프라인 재작성. `_HISTORY_LIMIT 10→6`. `_park_pending_turn` 제거. `_compose_system_prompt` 추가 |
| `app/services/rag/retrievers/hybrid.py` | 가중합 → RRF (vector + tsvector BM25). `_bm25_search` 추가 |
| `app/services/tools/rq_adapters.py` | `route_intent_via_rq` 제거 |
| `app/dtos/tools.py` | `RouteResult` 제거 |
| `ai_worker/domains/tool_calling/jobs.py` | `route_intent_job` 제거 + retry 적용 |
| `ai_worker/domains/rag/retrieval.py` | `encode_text` (ko-sroberta) → `encode_query` (OpenAI 3072d) |
| `ai_worker/domains/rag/jobs.py` | `embed_text_job` 제거. `generate_chat_response_job` 만 |
| `ai_worker/main.py` | `warmup_embedding_model` 제거 |
| `pyproject.toml` | `torch / torchvision / sentence-transformers` 의존 제거 |
| `ai_worker/Dockerfile{,.prod}` | ko-sroberta pre-download / `HF_HOME` ENV 제거 |
| `docker-compose.prod.yml` | `hf_cache` named volume + ENV 제거 |

---

## 3. 단위 테스트 (55 / 55 통과)

| 파일 | 케이스 |
|---|---|
| `test_retry_decorator.py` | 4 (성공 1회 후 재시도, max_attempts 모두 실패, non-retryable, decorator factory) |
| `test_context_format.py` | 4 (basic / empty / cap / truncate) |
| `test_openai_embedding.py` | 7 (constants 2 + encode_query 3 + batch 2) |
| `test_rrf.py` | 8 (constants 1 + merge 2 + intra 2 + cross 3) |
| `test_intent_classifier.py` | 10 (schema 4 + classify 6) |
| `test_medical_context.py` | 4 (full / no_survey / no_medication / empty) |
| `test_intent_orchestrator.py` | 3 (medical_context 전달 + 빈 ctx 처리 + 결과 propagate) |
| `test_fanout_tool_calls.py` | 4 (3 queries / empty / None / unique ids) |
| `test_rag_context_assembler.py` | 6 (basic / empty / errors / dedup / cap / mixed) |
| `test_ask_with_tools_e2e.py` | 5 (greeting / 5-1 full pipeline / referent / fallback / rollback) |

---

## 4. 운영 영향 + 검증

### 본 PR 머지 시 자동배포 영향

| 영역 | 영향 |
|---|---|
| 마이그레이션 | **변경 없음** — 28번 마이그는 이미 직전 PR 에서 적용됨 |
| Docker 이미지 사이즈 | ai-worker **~1.7GB 감소 예상** (PyTorch + sentence-transformers 제거) |
| 첫 부팅 시간 | ko-sroberta 로딩 (~30초) 사라져 단축 |
| `hf_cache` 볼륨 | 자동배포 후 **사용 안됨** (manual `docker volume rm ai_02_06_hf_cache`) |
| OpenAI API 호출 | 한 turn 당: 4o-mini 1회 + Embedding 1회 + 4o 1회 |
| 운영 비용 | turn 당 ~$0.025 추정 (~30원) |

### 5-1 시나리오 검증 가능 상태

이전 PR 에서 medicine_chunk 에 ~309K chunks 임베딩 완료 (사용자 4개 복용약 + 동의어 + 일반 의약품 일부, $2.32). 본 PR 머지 + 자동배포 후:

```
사용자: "타이레놀 먹어도 돼?"
↓ Step 0: medication=[메트포민, 와파린, 오메가3, 타이레놀] + survey 로드
↓ Step 1+2: 4o-mini → fanout 5~7 queries
↓ Step 3: search_medicine_knowledge_base × 5~7 (RRF) → 15 unique chunks
↓ Step 4: RAG context inject + 4o → "와파린과 병용 시 INR 상승 ..." 답변
```

기대 답변: 와파린 출혈 위험 + 알레르기 가드 + 기저질환 (간/신장) 주의 모두 포함.

---

## 5. 폐기된 결정 + 최종 결정 매트릭스 (PLAN.md §0 정리)

| 항목 | 최종 결정 | 사유 |
|---|---|---|
| 임베딩 모델 | OpenAI text-embedding-3-large (3072d) | ko-sroberta 한국어 의약품 매칭 한계 |
| 인프라 | hf_cache / HF_* ENV / sentence-transformers 즉시 정리 | 사용처 0 |
| **A** profile filter | medicine_chunk 는 공통 마스터데이터 (profile_id 컬럼 X) | 도메인 정합 |
| **B** Step 1+2 | 4o-mini IntentClassifier 통합 | 1 LLM 호출 절약 |
| **C** Hybrid | RRF (intra-query) + tsvector | 표준 알고리즘 |
| **D** Retry | 자체 구현 ~50라인 | 외부 의존 X |
| **E** get_weather tool | 보류 | 5-1 무관 |
| **F** Context inject | `[약: name][section]: chunk` system prompt | F1 정공 |
| Fan-out cap | 10, 임상 우선순위 자율 cut, 음성응답 제외 | DB pool 안전 |
| Retrieval | 각 query K=5 + final_cap=15 | lost-in-middle 회피 |
| recent history | **6 messages** (3 user + 3 assistant) | 6-turn compact 정합 |
| 2nd LLM user role | **raw query 그대로** (canonical 폐기) | UX 일관성 |
| referent_resolution | system `[명확화]` 섹션 | 대명사 풀이 |

---

## 6. 다음 단계 (본 PR 후속)

| 우선순위 | 작업 |
|---|---|
| **즉시** | 본 PR push + GitHub PR 생성 → 사용자 review → 머지 |
| 운영 검증 | EC2 자동배포 후 5-1 시나리오 e2e 호출 → 답변 품질 측정 |
| 답변 튜닝 | 4o system_prompt 의 톤/룰 조정 (별도 작은 PR) |
| ANN 인덱스 | medicine_chunk 의 vector(3072) 에 Matryoshka 768d subspace 또는 dim 축소 → HNSW (별도 PR) |
| 운영 EC2 cleanup | `docker volume rm ai_02_06_hf_cache` (자동배포 후 안전한 시점) |
| chain 정상화 | `refactor/migrations-normalize` PR (별도 큰 작업, 보류 결정) |

---

## 7. 8 Commits 명세

```
fe4beb3  feat(rag): e2e mock + Docker/의존 정리 (Phase 4-7/4-8 완성)
(이전)   feat(rag): retry + HybridRetriever RRF + ko-sroberta 폐기 (Phase 4-5/6)
(이전)   feat(rag): MessageService 4단 파이프라인 통합 + Router LLM 폐기 (Phase 4-2/3/4)
b488c19  feat(rag): classify_user_turn 오케스트레이터 (Phase 4-1)
a060c87  feat(rag): medical_context + IntentClassifier 4o-mini (Phase 3-B)
a280404  feat(rag): retry / context_format / openai_embedding / RRF 4모듈 (Phase 3-A)
9fff867  test(rag): 4단 파이프라인 단위 테스트 6 파일 (Phase 2 Test - Red)
40af3d6  refactor(rag): RAG 4단 파이프라인 신규 모듈 7개 자리 마련 (Phase 1 Tidy)
```

---

## 8. 팀원 적용 가이드

본 PR 머지 후 팀원 로컬 환경:

```bash
git checkout main
git pull origin main

# torch / sentence-transformers 가 lock 에서 제거됨 — uv sync
docker compose down
uv sync --group app --group dev --frozen

# 컨테이너 재기동 (Dockerfile 변경 반영)
docker compose build fastapi ai-worker
docker compose up -d
```

→ ai-worker 첫 기동이 직전보다 ~30초 빠름 (ko-sroberta 로딩 사라짐).

향후 마이그 작성 시 룰 (`docs/MIGRATIONS_NORMALIZATION.md` §3.2):
- 모델 클래스 우선 → aerich migrate → SQL 만 수동 수정 → MODELS_STATE 보존
- raw SQL only 마이그 금지 (시나리오 A 절대 정책)
