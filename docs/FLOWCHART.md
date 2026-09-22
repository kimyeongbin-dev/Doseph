# 처방전 OCR · 챗봇 전체 흐름도


> **읽는 법**: 화살표 방향(→)으로 따라가면 됩니다.
> 다이아몬드(◇)는 "예/아니오" 질문, 직사각형(□)은 실제로 일어나는 일입니다.

---

## 1. 처방전 사진 → 약 정보 저장 흐름 (OCR)

```mermaid
flowchart TD
    START(["👤 사용자가<br />처방전 사진을 올림"])

    START --> VALIDATE{"사진이<br />올바른 형식인가?<br />(jpg·png·webp, 5MB 이하)"}
    VALIDATE -- "❌ 아니오" --> ERR_FILE["⚠️ 오류 메시지를 보여주고<br />다시 올려달라고 안내"]
    VALIDATE -- "✅ 예" --> SAVE_TEMP["📱 브라우저가 사진을<br />임시 보관함(SessionStorage)에<br />잠깐 저장해 둠"]

    SAVE_TEMP --> LOADING["⏳ '분석 중...' 화면으로 이동<br />로딩 애니메이션 표시"]

    LOADING --> PHASE1

    subgraph PHASE1 ["🖥️ 서버 작업 1단계 — 글자 읽기 · DB 매칭"]
        OCR["🔍 Clova OCR<br />사진 속 글자를 모두 읽어냄<br />(네이버 AI 서비스 활용)"]
        OCR_FAIL{"글자를<br />읽었나?"}
        DB_MATCH["🗄️ 약품 DB와 이름 매칭<br />(OCR 결과 → DB 검색)"]
        MATCH_RESULT{"DB에서<br />약품을 찾았나?"}
        USER_INPUT["✏️ 사용자에게 직접 입력 요청<br />(매칭 실패 항목 수동 입력)"]
        REDIS["💾 Redis(임시 창고)에<br />매칭된 결과를 저장<br />10분 후 자동 삭제됨"]
        DRAFT_ID["🔑 임시 열쇠(draft_id)를<br />사용자에게 돌려줌"]

        OCR --> OCR_FAIL
        OCR_FAIL -- "❌ 실패" --> ERR_OCR["⚠️ 오류: 다시 찍어주세요"]
        OCR_FAIL -- "✅ 성공" --> DB_MATCH
        DB_MATCH --> MATCH_RESULT
        MATCH_RESULT -- "❌ 미매칭" --> USER_INPUT
        MATCH_RESULT -- "✅ 매칭" --> REDIS
        USER_INPUT --> REDIS
        REDIS --> DRAFT_ID
    end

    ERR_OCR --> ERR_FILE

    DRAFT_ID --> BROWSER_CLEAN["🗑️ 브라우저 임시 보관함 삭제<br />'분석 완료!' 안내창 표시"]
    BROWSER_CLEAN --> RESULT_PAGE["📋 결과 페이지로 이동"]

    subgraph PHASE2 ["🖥️ 서버 작업 2단계 — 임시 저장 결과 불러오기"]
        FETCH_DRAFT["임시 열쇠로 Redis에서<br />정리된 약품 목록 조회"]
        DRAFT_EXIST{"10분 안에<br />조회했나?"}
        RETURN_LIST["약품 목록 데이터 반환"]
        ERR_EXPIRED["⚠️ 오류: 시간이 지났어요<br />처음부터 다시 해주세요"]

        FETCH_DRAFT --> DRAFT_EXIST
        DRAFT_EXIST -- "❌ 만료됨" --> ERR_EXPIRED
        DRAFT_EXIST -- "✅ 있음" --> RETURN_LIST
    end

    RESULT_PAGE --> FETCH_DRAFT
    ERR_EXPIRED --> START

    RETURN_LIST --> USER_EDIT["✏️ 사용자가 약품 카드를<br />확인하고 잘못된 부분 수정·삭제"]
    USER_EDIT --> CONFIRM{"확정 버튼<br />클릭?"}
    CONFIRM -- "아직 수정 중" --> USER_EDIT

    CONFIRM -- "✅ 확정!" --> PHASE3

    subgraph PHASE3 ["🖥️ 서버 작업 3단계 — 최종 저장 · 가이드 생성"]
        ATOMIC_DELETE{"Redis에서<br />데이터 삭제 성공?<br />(중복 저장 방지)"}
        DB_SAVE["🗄️ 데이터베이스(PostgreSQL)에<br />약품 정보를 영구 저장"]
        RESPOND_201["✅ '저장 완료!' 응답 즉시 반환"]
        BG_GUIDE[["⚙️ 백그라운드 작업<br />GPT가 복약 가이드 생성<br />(5~15초 소요, 별도 진행)"]]

        ATOMIC_DELETE -- "❌ 0 (이미 처리됨)" --> ERR_DUPLICATE["⚠️ 중복 요청 차단<br />새로 등록해주세요"]
        ATOMIC_DELETE -- "✅ 1 (정상)" --> DB_SAVE
        DB_SAVE --> RESPOND_201
        RESPOND_201 --> BG_GUIDE
    end

    PHASE3 --> MAIN_PAGE["🏠 메인 페이지로 이동<br />저장된 약품 목록 확인 가능"]

    style PHASE1 fill:#eef2ff,stroke:#6366f1,color:#1e1b4b
    style PHASE2 fill:#f0fdf4,stroke:#22c55e,color:#14532d
    style PHASE3 fill:#fff7ed,stroke:#f97316,color:#7c2d12
    style BG_GUIDE fill:#fefce8,stroke:#eab308
    style ERR_FILE fill:#fef2f2,stroke:#ef4444
    style ERR_OCR fill:#fef2f2,stroke:#ef4444
    style ERR_EXPIRED fill:#fef2f2,stroke:#ef4444
    style ERR_DUPLICATE fill:#fef2f2,stroke:#ef4444
```

---

## 2. 챗봇 흐름 (약사 AI와 대화)

```mermaid
flowchart TD
    U_START(["👤 사용자가 챗봇 페이지 열기"])

    U_START --> CREATE_SESSION["💬 새 채팅방 만들기<br />(어떤 약에 대해 물어볼지 선택 가능)"]
    CREATE_SESSION --> INPUT["⌨️ 궁금한 점을 입력<br />예: '이 약 졸리나요?'"]
    INPUT --> SEND["📤 질문 전송"]

    SEND --> RAG_PIPELINE

    subgraph RAG_PIPELINE ["🧠 RAG 파이프라인 (AI가 답을 찾는 과정)"]
        direction TB
        EMB["1️⃣ 질문을 숫자 벡터로 변환<br />(텍스트 임베딩 — AI가 뜻을 수치로 표현)"]
        SEARCH["2️⃣ 약품 데이터베이스에서<br />가장 비슷한 정보 3개 찾기<br />(pgvector 코사인 유사도 검색)"]
        BUILD_CONTEXT["3️⃣ 찾은 정보를 묶어<br />'참고 자료'로 만들기"]
        GPT_CALL["4️⃣ GPT-4o-mini 호출<br />참고 자료 + 질문을 함께 전달<br />'Doseph' 약사 캐릭터로 답변 생성"]
        GPT_ANSWER{"답변<br />생성 성공?"}

        EMB --> SEARCH
        SEARCH --> BUILD_CONTEXT
        BUILD_CONTEXT --> GPT_CALL
        GPT_CALL --> GPT_ANSWER
    end

    GPT_ANSWER -- "✅ 성공" --> SHOW_ANSWER["💬 친절한 약사 말투로<br />답변 화면에 표시"]
    GPT_ANSWER -- "❌ 실패" --> SHOW_ERR["⚠️ '잠시 후 다시<br />말씀해 주세요' 안내"]

    SHOW_ANSWER --> CONTINUE{"더 물어볼<br />것이 있나요?"}
    CONTINUE -- "✅ 예" --> INPUT
    CONTINUE -- "❌ 아니오" --> END(["✅ 대화 종료"])

    style RAG_PIPELINE fill:#f5f3ff,stroke:#7c3aed,color:#1e1b4b
    style GPT_CALL fill:#ede9fe,stroke:#7c3aed
    style SHOW_ERR fill:#fef2f2,stroke:#ef4444
```

---

## 3. RAG 파이프라인 상세 (AI가 정확한 답을 찾는 방법)

> **RAG(검색 증강 생성)란?**
> AI가 답을 **지어내지 않고**, 실제 약품 데이터베이스에서 **관련 정보를 먼저 찾은 뒤** 그 정보를 바탕으로 대답하는 방식입니다.
> 마치 의사가 답하기 전에 의학 교과서를 찾아보는 것과 같아요.

```mermaid
flowchart LR
    Q["❓ 사용자 질문<br />예: '타이레놀<br />언제 먹어요?'"]

    subgraph EMBED ["① 질문 이해하기"]
        E1["OpenAI text-embedding-3-large<br />(원격 API)"]
        E2["질문 → 숫자 벡터 (3072차원)<br />[0.12, -0.87, 0.34 ...]"]
        E1 --> E2
    end

    subgraph RETRIEVE ["② 관련 정보 찾기"]
        R1["pgvector DB<br />medicine_info 테이블"]
        R2["코사인 유사도로<br />가장 비슷한 약품 정보<br />최대 3개 선택"]
        R3["약품명·효능·<br />부작용·주의사항<br />텍스트로 변환"]
        R1 --> R2 --> R3
    end

    subgraph GENERATE ["③ 답변 만들기"]
        G1["시스템 프롬프트<br />+ 참고 자료<br />+ 사용자 질문"]
        G2["GPT-4o-mini 호출<br />temperature: 0.7"]
        G3["🗣️ Doseph 약사<br />말투로 최종 답변 생성<br />(최대 800 토큰)"]
        G1 --> G2 --> G3
    end

    Q --> EMBED
    E2 --> RETRIEVE
    R3 --> GENERATE

    G3 --> A["💬 사용자 화면에<br />답변 표시"]

    style EMBED fill:#eff6ff,stroke:#3b82f6,color:#1e3a8a
    style RETRIEVE fill:#f0fdf4,stroke:#22c55e,color:#14532d
    style GENERATE fill:#fdf4ff,stroke:#a855f7,color:#581c87
```

---

## 단계별 핵심 정리

| 단계 | 무슨 일이 일어나나요? | 사용하는 기술 |
|------|----------------------|--------------|
| **OCR 1단계** | 처방전 사진 → 글자 읽기 → 약품 DB 매칭 (미매칭 시 사용자 직접 입력) | Clova OCR + PostgreSQL |
| **OCR 2단계** | 매칭된 결과를 불러와 사용자가 확인·수정 | Redis (임시 저장소) |
| **OCR 3단계** | 최종 확정 후 DB 저장 + 복약 가이드 생성 | PostgreSQL + GPT-4o-mini |
| **챗봇** | 사용자 질문에 약사 AI가 답변 | RAG + GPT-4o-mini |
| **RAG** | 답하기 전에 실제 약품 DB에서 정보 검색 | OpenAI text-embedding-3-large + pgvector(halfvec) |
