from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS "accounts" (
    "id" UUID NOT NULL PRIMARY KEY,
    "auth_provider" VARCHAR(16) NOT NULL,
    "provider_account_id" VARCHAR(128) NOT NULL,
    "nickname" VARCHAR(32) NOT NULL,
    "profile_image_url" VARCHAR(512),
    "is_active" BOOL NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ,
    CONSTRAINT "uid_accounts_auth_pr_8579f6" UNIQUE ("auth_provider", "provider_account_id")
);
COMMENT ON COLUMN "accounts"."auth_provider" IS 'KAKAO: KAKAO\nNAVER: NAVER';
COMMENT ON TABLE "accounts" IS 'Account model for storing user authentication information.';
CREATE TABLE IF NOT EXISTS "refresh_tokens" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "token_hash" VARCHAR(64) NOT NULL,
    "expires_at" TIMESTAMPTZ NOT NULL,
    "is_revoked" BOOL NOT NULL DEFAULT False,
    "rotated_at" TIMESTAMPTZ,
    "replaced_by_id" BIGINT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "account_id" UUID NOT NULL REFERENCES "accounts" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_refresh_tok_token_h_e92003" ON "refresh_tokens" ("token_hash");
CREATE INDEX IF NOT EXISTS "idx_refresh_tok_account_b96f59" ON "refresh_tokens" ("account_id", "is_revoked");
COMMENT ON COLUMN "refresh_tokens"."id" IS 'Token record ID';
COMMENT ON COLUMN "refresh_tokens"."token_hash" IS 'SHA-256 hash of refresh token';
COMMENT ON COLUMN "refresh_tokens"."expires_at" IS 'Token expiration timestamp';
COMMENT ON COLUMN "refresh_tokens"."is_revoked" IS 'Token revocation status (logout or RTR)';
COMMENT ON COLUMN "refresh_tokens"."rotated_at" IS 'Token rotation timestamp (for Grace Period calculation)';
COMMENT ON COLUMN "refresh_tokens"."replaced_by_id" IS 'ID of replacement token (for tracking)';
COMMENT ON COLUMN "refresh_tokens"."created_at" IS 'Token issuance timestamp';
COMMENT ON COLUMN "refresh_tokens"."account_id" IS 'Token owner account';
COMMENT ON TABLE "refresh_tokens" IS 'Refresh token management model.';
CREATE TABLE IF NOT EXISTS "profiles" (
    "id" UUID NOT NULL PRIMARY KEY,
    "relation_type" VARCHAR(16) NOT NULL,
    "gender" VARCHAR(8),
    "name" VARCHAR(32) NOT NULL,
    "health_survey" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ,
    "account_id" UUID NOT NULL REFERENCES "accounts" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_profiles_account_bac81d" ON "profiles" ("account_id", "relation_type");
COMMENT ON COLUMN "profiles"."relation_type" IS 'SELF: SELF\nFATHER: FATHER\nMOTHER: MOTHER\nSON: SON\nDAUGHTER: DAUGHTER\nHUSBAND: HUSBAND\nWIFE: WIFE\nOTHER: OTHER';
COMMENT ON COLUMN "profiles"."gender" IS 'MALE: MALE\nFEMALE: FEMALE';
COMMENT ON TABLE "profiles" IS 'Profile model for storing user and family member information.';
CREATE TABLE IF NOT EXISTS "prescription_groups" (
    "id" UUID NOT NULL PRIMARY KEY,
    "hospital_name" VARCHAR(128),
    "department" VARCHAR(64),
    "dispensed_date" DATE,
    "source" VARCHAR(16) NOT NULL DEFAULT 'OCR',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ,
    "profile_id" UUID NOT NULL REFERENCES "profiles" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_prescriptio_profile_123bd2" ON "prescription_groups" ("profile_id", "dispensed_date");
CREATE INDEX IF NOT EXISTS "idx_prescriptio_profile_2416cb" ON "prescription_groups" ("profile_id", "deleted_at");
COMMENT ON COLUMN "prescription_groups"."hospital_name" IS '처방전 발행 병원 이름';
COMMENT ON COLUMN "prescription_groups"."department" IS '처방 진료과 (내과/소아과 등)';
COMMENT ON COLUMN "prescription_groups"."dispensed_date" IS '처방 조제일 — 그룹 매핑 키';
COMMENT ON COLUMN "prescription_groups"."source" IS '생성 경로 (OCR/MANUAL/MIGRATED)';
COMMENT ON COLUMN "prescription_groups"."profile_id" IS '처방전 소유 프로필';
COMMENT ON TABLE "prescription_groups" IS '처방전 그룹 — medication / lifestyle_guide / challenge 의 부모 단위.';
CREATE TABLE IF NOT EXISTS "medications" (
    "id" UUID NOT NULL PRIMARY KEY,
    "medicine_name" VARCHAR(128) NOT NULL,
    "department" VARCHAR(64),
    "category" VARCHAR(64),
    "dose_per_intake" VARCHAR(32),
    "daily_intake_count" INT,
    "total_intake_days" INT,
    "intake_instruction" VARCHAR(256),
    "raw_ocr_name" VARCHAR(128),
    "is_llm_corrected" BOOL NOT NULL DEFAULT False,
    "match_score" DOUBLE PRECISION,
    "intake_times" JSONB NOT NULL,
    "total_intake_count" INT NOT NULL,
    "remaining_intake_count" INT NOT NULL,
    "start_date" DATE NOT NULL,
    "end_date" DATE,
    "dispensed_date" DATE,
    "expiration_date" DATE,
    "is_active" BOOL NOT NULL DEFAULT True,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ,
    "prescription_group_id" UUID REFERENCES "prescription_groups" ("id") ON DELETE CASCADE,
    "profile_id" UUID NOT NULL REFERENCES "profiles" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_medications_profile_c1211f" ON "medications" ("profile_id", "is_active");
COMMENT ON COLUMN "medications"."medicine_name" IS '약품명';
COMMENT ON COLUMN "medications"."department" IS '처방 진료과 (예: 내과)';
COMMENT ON COLUMN "medications"."category" IS '약품 분류 (예: 해열진통제)';
COMMENT ON COLUMN "medications"."dose_per_intake" IS '1회 복용량 (예: 1정, 5ml)';
COMMENT ON COLUMN "medications"."daily_intake_count" IS '1일 복용 횟수';
COMMENT ON COLUMN "medications"."total_intake_days" IS '총 복용 일수';
COMMENT ON COLUMN "medications"."intake_instruction" IS '복용 지시사항';
COMMENT ON COLUMN "medications"."raw_ocr_name" IS 'OCR이 인식한 날것의 텍스트 (수동 입력 시 null, BE 트래킹 전용)';
COMMENT ON COLUMN "medications"."is_llm_corrected" IS 'LLM 또는 퍼지 매칭으로 교정된 약품인지 여부 (BE 트래킹 전용)';
COMMENT ON COLUMN "medications"."match_score" IS '퍼지 매칭 또는 LLM 유사도/신뢰도 점수 (0.0 ~ 1.0, BE 트래킹 전용)';
COMMENT ON COLUMN "medications"."intake_times" IS 'Daily intake times list';
COMMENT ON COLUMN "medications"."total_intake_count" IS 'Total prescribed intake count';
COMMENT ON COLUMN "medications"."remaining_intake_count" IS 'Remaining intake count';
COMMENT ON COLUMN "medications"."start_date" IS 'Medication start date';
COMMENT ON COLUMN "medications"."end_date" IS 'Expected end date';
COMMENT ON COLUMN "medications"."dispensed_date" IS 'Medication dispensing date';
COMMENT ON COLUMN "medications"."expiration_date" IS 'Medication expiration date';
COMMENT ON COLUMN "medications"."is_active" IS 'Currently taking medication';
COMMENT ON COLUMN "medications"."prescription_group_id" IS '소속 처방전 그룹 (한 번의 진료/처방 단위)';
COMMENT ON TABLE "medications" IS 'Medication model for prescription tracking.';
CREATE TABLE IF NOT EXISTS "medicine_info" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "item_seq" VARCHAR(20) UNIQUE,
    "medicine_name" VARCHAR(200) NOT NULL UNIQUE,
    "item_eng_name" VARCHAR(256),
    "entp_name" VARCHAR(128),
    "product_type" VARCHAR(64),
    "spclty_pblc" VARCHAR(32),
    "permit_date" VARCHAR(8),
    "cancel_name" VARCHAR(16),
    "main_item_ingr" TEXT,
    "storage_method" TEXT,
    "edi_code" VARCHAR(256),
    "bizrno" VARCHAR(16),
    "change_date" VARCHAR(8),
    "category" VARCHAR(64),
    "efficacy" TEXT,
    "side_effects" JSONB,
    "precautions" JSONB,
    "dosage" TEXT,
    "chart" TEXT,
    "material_name" TEXT,
    "valid_term" VARCHAR(64),
    "pack_unit" VARCHAR(2048),
    "atc_code" VARCHAR(32),
    "ee_doc_url" VARCHAR(256),
    "ud_doc_url" VARCHAR(256),
    "nb_doc_url" VARCHAR(256),
    "ee_doc_data" TEXT,
    "ud_doc_data" TEXT,
    "nb_doc_data" TEXT,
    "last_synced_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON COLUMN "medicine_info"."item_seq" IS 'Drug product code from public API (UPSERT key)';
COMMENT ON COLUMN "medicine_info"."medicine_name" IS 'Drug product name in Korean';
COMMENT ON COLUMN "medicine_info"."item_eng_name" IS 'Drug product name in English';
COMMENT ON COLUMN "medicine_info"."entp_name" IS 'Manufacturer name';
COMMENT ON COLUMN "medicine_info"."product_type" IS 'Product classification code';
COMMENT ON COLUMN "medicine_info"."spclty_pblc" IS 'Professional or OTC drug classification';
COMMENT ON COLUMN "medicine_info"."permit_date" IS 'Permit date in YYYYMMDD format';
COMMENT ON COLUMN "medicine_info"."cancel_name" IS 'Current status (normal or cancelled)';
COMMENT ON COLUMN "medicine_info"."main_item_ingr" IS 'Active ingredients with standard codes';
COMMENT ON COLUMN "medicine_info"."storage_method" IS 'Storage method and instructions';
COMMENT ON COLUMN "medicine_info"."edi_code" IS 'Insurance billing codes (comma-separated)';
COMMENT ON COLUMN "medicine_info"."bizrno" IS 'Business registration number';
COMMENT ON COLUMN "medicine_info"."change_date" IS 'Last change date from API in YYYYMMDD format';
COMMENT ON COLUMN "medicine_info"."category" IS 'Drug category for search filtering';
COMMENT ON COLUMN "medicine_info"."efficacy" IS 'Drug efficacy and effects';
COMMENT ON COLUMN "medicine_info"."side_effects" IS '이상반응 PARAGRAPH list (NB_DOC_DATA 4번 이상반응 카테고리)';
COMMENT ON COLUMN "medicine_info"."precautions" IS '식약처 9 카테고리(이상반응 제외) dict';
COMMENT ON COLUMN "medicine_info"."dosage" IS '용법용량 평문화 (UD_DOC_DATA → flatten plaintext)';
COMMENT ON COLUMN "medicine_info"."chart" IS 'Physical appearance (CHART)';
COMMENT ON COLUMN "medicine_info"."material_name" IS 'Total/portion raw string (MATERIAL_NAME)';
COMMENT ON COLUMN "medicine_info"."valid_term" IS 'Shelf-life description (VALID_TERM)';
COMMENT ON COLUMN "medicine_info"."pack_unit" IS 'Packaging unit description (PACK_UNIT) — 일부 품목은 256 자 초과 가능';
COMMENT ON COLUMN "medicine_info"."atc_code" IS 'WHO ATC classification code (ATC_CODE)';
COMMENT ON COLUMN "medicine_info"."ee_doc_url" IS 'Efficacy PDF source URL (EE_DOC_ID)';
COMMENT ON COLUMN "medicine_info"."ud_doc_url" IS 'Usage PDF source URL (UD_DOC_ID)';
COMMENT ON COLUMN "medicine_info"."nb_doc_url" IS 'Precaution PDF source URL (NB_DOC_ID)';
COMMENT ON COLUMN "medicine_info"."ee_doc_data" IS 'Raw EE_DOC_DATA XML (효능효과 원문)';
COMMENT ON COLUMN "medicine_info"."ud_doc_data" IS 'Raw UD_DOC_DATA XML (용법용량 원문)';
COMMENT ON COLUMN "medicine_info"."nb_doc_data" IS 'Raw NB_DOC_DATA XML (사용상주의사항 원문)';
COMMENT ON COLUMN "medicine_info"."last_synced_at" IS 'Last synchronization timestamp from public API';
COMMENT ON TABLE "medicine_info" IS 'Pharmaceutical knowledge base for RAG search and public API data';
CREATE TABLE IF NOT EXISTS "medicine_chunk" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "section" VARCHAR(48) NOT NULL,
    "chunk_index" INT NOT NULL DEFAULT 0,
    "content" TEXT NOT NULL,
    "token_count" INT,
    "embedding" TEXT,
    "model_version" VARCHAR(64) NOT NULL,
    "interaction_tags" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "medicine_info_id" INT NOT NULL REFERENCES "medicine_info" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_medicine_ch_medicin_e873e2" UNIQUE ("medicine_info_id", "section", "chunk_index")
);
CREATE INDEX IF NOT EXISTS "idx_medicine_ch_medicin_68dcca" ON "medicine_chunk" ("medicine_info_id");
CREATE INDEX IF NOT EXISTS "idx_medicine_ch_section_af179e" ON "medicine_chunk" ("section");
CREATE INDEX IF NOT EXISTS "idx_medicine_ch_model_v_6d67cd" ON "medicine_chunk" ("model_version");
COMMENT ON COLUMN "medicine_chunk"."section" IS 'Chunk section tag (MedicineChunkSection)';
COMMENT ON COLUMN "medicine_chunk"."chunk_index" IS 'Sub-chunk order when ARTICLE is split by token limit';
COMMENT ON COLUMN "medicine_chunk"."content" IS 'Final embedding-target text with header prefix';
COMMENT ON COLUMN "medicine_chunk"."token_count" IS 'Token count for monitoring';
COMMENT ON COLUMN "medicine_chunk"."embedding" IS 'pgvector VECTOR(768) - materialised via manual SQL';
COMMENT ON COLUMN "medicine_chunk"."model_version" IS 'Embedding model version (e.g. ko-sroberta-multitask-v1)';
COMMENT ON COLUMN "medicine_chunk"."interaction_tags" IS 'JSONB array of interaction tags (see interaction_tags.json)';
COMMENT ON COLUMN "medicine_chunk"."medicine_info_id" IS 'Parent medicine_info reference';
COMMENT ON TABLE "medicine_chunk" IS 'Section-level embedding chunks for RAG similarity search';
CREATE TABLE IF NOT EXISTS "medicine_ingredient" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "mtral_sn" INT NOT NULL,
    "mtral_code" VARCHAR(16),
    "mtral_name" VARCHAR(128) NOT NULL,
    "main_ingr_eng" VARCHAR(256),
    "quantity" VARCHAR(32),
    "unit" VARCHAR(16),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "medicine_info_id" INT NOT NULL REFERENCES "medicine_info" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_medicine_in_medicin_8f85f4" UNIQUE ("medicine_info_id", "mtral_sn")
);
CREATE INDEX IF NOT EXISTS "idx_medicine_in_mtral_n_3e3034" ON "medicine_ingredient" ("mtral_name");
CREATE INDEX IF NOT EXISTS "idx_medicine_in_mtral_c_705f45" ON "medicine_ingredient" ("mtral_code");
COMMENT ON COLUMN "medicine_ingredient"."mtral_sn" IS 'Ingredient sequence number within the drug (API MTRAL_SN)';
COMMENT ON COLUMN "medicine_ingredient"."mtral_code" IS 'Ingredient standard code (API MTRAL_CODE)';
COMMENT ON COLUMN "medicine_ingredient"."mtral_name" IS 'Korean ingredient name (API MTRAL_NM)';
COMMENT ON COLUMN "medicine_ingredient"."main_ingr_eng" IS 'English ingredient name (API MAIN_INGR_ENG)';
COMMENT ON COLUMN "medicine_ingredient"."quantity" IS 'Ingredient quantity (API QNT)';
COMMENT ON COLUMN "medicine_ingredient"."unit" IS 'Quantity unit (API INGD_UNIT_CD)';
COMMENT ON COLUMN "medicine_ingredient"."medicine_info_id" IS 'Parent medicine_info reference';
COMMENT ON TABLE "medicine_ingredient" IS 'Drug active ingredients (1:N from medicine_info)';
CREATE TABLE IF NOT EXISTS "lifestyle_guides" (
    "id" UUID NOT NULL PRIMARY KEY,
    "status" VARCHAR(16) NOT NULL DEFAULT 'pending',
    "content" JSONB NOT NULL,
    "medication_snapshot" JSONB NOT NULL,
    "input_fingerprint" VARCHAR(64),
    "revealed_challenge_count" INT NOT NULL DEFAULT 5,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "processed_at" TIMESTAMPTZ,
    "prescription_group_id" UUID REFERENCES "prescription_groups" ("id") ON DELETE CASCADE,
    "profile_id" UUID NOT NULL REFERENCES "profiles" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_lifestyle_g_profile_1772b1" ON "lifestyle_guides" ("profile_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_lifestyle_g_profile_58f8f3" ON "lifestyle_guides" ("profile_id", "input_fingerprint");
COMMENT ON COLUMN "lifestyle_guides"."status" IS 'Async generation status (pending/ready/no_active_meds/failed)';
COMMENT ON COLUMN "lifestyle_guides"."content" IS 'GPT-generated guide content (5 categories)';
COMMENT ON COLUMN "lifestyle_guides"."medication_snapshot" IS 'Active medication list at guide generation time';
COMMENT ON COLUMN "lifestyle_guides"."input_fingerprint" IS 'SHA-256 hex of canonical input (medications + survey + prompt_ver)';
COMMENT ON COLUMN "lifestyle_guides"."revealed_challenge_count" IS '현재까지 사용자에게 노출한 챌린지 개수 (5 → 10 → 15)';
COMMENT ON COLUMN "lifestyle_guides"."processed_at" IS 'Terminal-status set time';
COMMENT ON COLUMN "lifestyle_guides"."prescription_group_id" IS '가이드가 만들어진 처방전 그룹 (신규부터 set)';
COMMENT ON COLUMN "lifestyle_guides"."profile_id" IS 'Guide owner profile';
COMMENT ON TABLE "lifestyle_guides" IS 'Lifestyle guide model for GPT-generated medication lifestyle advice.';
CREATE TABLE IF NOT EXISTS "daily_symptom_logs" (
    "id" UUID NOT NULL PRIMARY KEY,
    "log_date" DATE NOT NULL,
    "symptoms" JSONB NOT NULL,
    "note" VARCHAR(512),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "profile_id" UUID NOT NULL REFERENCES "profiles" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_daily_sympt_profile_1a0c84" ON "daily_symptom_logs" ("profile_id", "log_date");
COMMENT ON COLUMN "daily_symptom_logs"."log_date" IS 'Date of symptom report';
COMMENT ON COLUMN "daily_symptom_logs"."symptoms" IS 'List of reported symptoms';
COMMENT ON COLUMN "daily_symptom_logs"."note" IS 'Free-text note';
COMMENT ON COLUMN "daily_symptom_logs"."profile_id" IS 'Log owner profile';
COMMENT ON TABLE "daily_symptom_logs" IS 'Daily symptom log for tracking user-reported health symptoms.';
CREATE TABLE IF NOT EXISTS "challenges" (
    "id" UUID NOT NULL PRIMARY KEY,
    "category" VARCHAR(16),
    "title" VARCHAR(64) NOT NULL,
    "description" VARCHAR(256),
    "target_days" INT NOT NULL,
    "completed_dates" JSONB NOT NULL,
    "difficulty" VARCHAR(16),
    "challenge_status" VARCHAR(16) NOT NULL DEFAULT 'IN_PROGRESS',
    "is_active" BOOL NOT NULL DEFAULT False,
    "started_at" TIMESTAMPTZ,
    "completed_at" TIMESTAMPTZ,
    "started_date" DATE NOT NULL,
    "slot_index" INT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ,
    "guide_id" UUID REFERENCES "lifestyle_guides" ("id") ON DELETE CASCADE,
    "prescription_group_id" UUID REFERENCES "prescription_groups" ("id") ON DELETE CASCADE,
    "profile_id" UUID NOT NULL REFERENCES "profiles" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_challenges_profile_281206" ON "challenges" ("profile_id", "challenge_status");
COMMENT ON COLUMN "challenges"."category" IS 'Lifestyle category (diet/sleep/exercise/symptom/interaction)';
COMMENT ON COLUMN "challenges"."title" IS 'Challenge title';
COMMENT ON COLUMN "challenges"."description" IS 'Detailed description';
COMMENT ON COLUMN "challenges"."target_days" IS 'Target completion days';
COMMENT ON COLUMN "challenges"."completed_dates" IS 'List of completion dates';
COMMENT ON COLUMN "challenges"."difficulty" IS '난이도 (쉬움/보통/어려움)';
COMMENT ON COLUMN "challenges"."challenge_status" IS '진행 상태';
COMMENT ON COLUMN "challenges"."is_active" IS 'User has started this challenge';
COMMENT ON COLUMN "challenges"."started_at" IS 'Datetime when user activated challenge';
COMMENT ON COLUMN "challenges"."completed_at" IS 'Datetime when challenge was completed';
COMMENT ON COLUMN "challenges"."started_date" IS '챌린지 시작 날짜';
COMMENT ON COLUMN "challenges"."slot_index" IS '가이드 내 챌린지 노출 순서 (0~14, NULL = legacy)';
COMMENT ON COLUMN "challenges"."guide_id" IS 'Source guide — None means user-created challenge';
COMMENT ON COLUMN "challenges"."prescription_group_id" IS '소속 처방전 그룹 (신규부터 set)';
COMMENT ON TABLE "challenges" IS 'Challenge model for tracking user health challenges.';
CREATE TABLE IF NOT EXISTS "chat_sessions" (
    "id" UUID NOT NULL PRIMARY KEY,
    "title" VARCHAR(64),
    "summary" TEXT,
    "summary_updated_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ,
    "account_id" UUID NOT NULL REFERENCES "accounts" ("id") ON DELETE CASCADE,
    "profile_id" UUID NOT NULL REFERENCES "profiles" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_chat_sessio_account_4a006a" ON "chat_sessions" ("account_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_chat_sessio_profile_ab074b" ON "chat_sessions" ("profile_id");
COMMENT ON COLUMN "chat_sessions"."summary" IS 'Compact medical-context summary (옵션 D)';
COMMENT ON COLUMN "chat_sessions"."summary_updated_at" IS 'Last successful compact run timestamp';
COMMENT ON TABLE "chat_sessions" IS 'Chat session model for storing conversation sessions.';
CREATE TABLE IF NOT EXISTS "messages" (
    "id" UUID NOT NULL PRIMARY KEY,
    "sender_type" VARCHAR(16) NOT NULL,
    "content" TEXT NOT NULL,
    "metadata" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deleted_at" TIMESTAMPTZ,
    "session_id" UUID NOT NULL REFERENCES "chat_sessions" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_messages_session_78394c" ON "messages" ("session_id", "created_at");
COMMENT ON COLUMN "messages"."sender_type" IS 'USER: USER\nASSISTANT: ASSISTANT';
COMMENT ON COLUMN "messages"."metadata" IS 'RAG debug/audit metadata (intent, medicine_names, scores, token usage)';
COMMENT ON TABLE "messages" IS 'Chat message model for conversation storage.';
CREATE TABLE IF NOT EXISTS "message_feedbacks" (
    "id" UUID NOT NULL PRIMARY KEY,
    "is_helpful" BOOL NOT NULL,
    "feedback_text" VARCHAR(256),
    "metadata" JSONB,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "message_id" UUID NOT NULL UNIQUE REFERENCES "messages" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "message_feedbacks" IS 'Message feedback model for user response evaluation.';
CREATE TABLE IF NOT EXISTS "intake_logs" (
    "id" UUID NOT NULL PRIMARY KEY,
    "scheduled_date" DATE NOT NULL,
    "scheduled_time" TIMETZ NOT NULL,
    "intake_status" VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED',
    "taken_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "medication_id" UUID NOT NULL REFERENCES "medications" ("id") ON DELETE CASCADE,
    "profile_id" UUID NOT NULL REFERENCES "profiles" ("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "idx_intake_logs_profile_ab6b26" ON "intake_logs" ("profile_id", "scheduled_date");
CREATE INDEX IF NOT EXISTS "idx_intake_logs_schedul_5eb536" ON "intake_logs" ("scheduled_date", "intake_status");
COMMENT ON COLUMN "intake_logs"."scheduled_date" IS 'Scheduled intake date';
COMMENT ON COLUMN "intake_logs"."scheduled_time" IS 'Scheduled intake time';
COMMENT ON COLUMN "intake_logs"."intake_status" IS 'Intake status';
COMMENT ON COLUMN "intake_logs"."taken_at" IS 'Actual intake completion time';
COMMENT ON TABLE "intake_logs" IS 'Intake log model for tracking medication intake.';
CREATE TABLE IF NOT EXISTS "data_sync_log" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "sync_type" VARCHAR(32) NOT NULL,
    "sync_date" TIMESTAMPTZ NOT NULL,
    "total_fetched" INT NOT NULL DEFAULT 0,
    "total_inserted" INT NOT NULL DEFAULT 0,
    "total_updated" INT NOT NULL DEFAULT 0,
    "status" VARCHAR(16) NOT NULL,
    "error_message" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "idx_data_sync_l_sync_ty_af36c6" ON "data_sync_log" ("sync_type", "status");
COMMENT ON COLUMN "data_sync_log"."sync_type" IS 'Sync target type (e.g. medicine_info)';
COMMENT ON COLUMN "data_sync_log"."sync_date" IS 'Sync execution timestamp';
COMMENT ON COLUMN "data_sync_log"."total_fetched" IS 'Total records fetched from API';
COMMENT ON COLUMN "data_sync_log"."total_inserted" IS 'Number of newly inserted records';
COMMENT ON COLUMN "data_sync_log"."total_updated" IS 'Number of updated existing records';
COMMENT ON COLUMN "data_sync_log"."status" IS 'Sync result status (SUCCESS / FAILED)';
COMMENT ON COLUMN "data_sync_log"."error_message" IS 'Error details when sync fails';
COMMENT ON TABLE "data_sync_log" IS 'Public API data synchronization history';
CREATE TABLE IF NOT EXISTS "ocr_drafts" (
    "id" UUID NOT NULL PRIMARY KEY,
    "status" VARCHAR(16) NOT NULL DEFAULT 'pending',
    "medicines" JSONB NOT NULL,
    "filename" VARCHAR(256),
    "image_hash" VARCHAR(64) NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "processed_at" TIMESTAMPTZ,
    "consumed_at" TIMESTAMPTZ,
    "profile_id" UUID NOT NULL REFERENCES "profiles" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "ocr_drafts"."status" IS 'pending / ready / no_text / no_candidates / failed';
COMMENT ON COLUMN "ocr_drafts"."medicines" IS 'ExtractedMedicine 리스트 (ai-worker 가 채움)';
COMMENT ON COLUMN "ocr_drafts"."filename" IS '원본 파일명';
COMMENT ON COLUMN "ocr_drafts"."image_hash" IS 'SHA256(image_bytes) — dedup 키';
COMMENT ON COLUMN "ocr_drafts"."processed_at" IS 'ai-worker 처리 완료 시각';
COMMENT ON COLUMN "ocr_drafts"."consumed_at" IS 'confirm 완료 시각 (NULL=활성)';
COMMENT ON COLUMN "ocr_drafts"."profile_id" IS '업로드 프로필';
COMMENT ON TABLE "ocr_drafts" IS '처방전 OCR 처리 결과 임시 저장 (24h, profile 별 회수 가능)';
CREATE TABLE IF NOT EXISTS "drug_recalls" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "item_seq" VARCHAR(20) NOT NULL,
    "std_code" VARCHAR(32),
    "product_name" VARCHAR(200) NOT NULL,
    "entrps_name" VARCHAR(128) NOT NULL,
    "entrps_name_normalized" VARCHAR(128) NOT NULL,
    "recall_reason" TEXT NOT NULL,
    "recall_command_date" VARCHAR(8) NOT NULL,
    "sale_stop_yn" VARCHAR(1) NOT NULL DEFAULT 'N',
    "is_hospital_only" BOOL NOT NULL DEFAULT False,
    "is_non_drug" BOOL NOT NULL DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "uid_drug_recall_item_se_3e2ee7" UNIQUE ("item_seq", "recall_command_date", "recall_reason")
);
CREATE INDEX IF NOT EXISTS "idx_drug_recall_entrps__ed75fc" ON "drug_recalls" ("entrps_name_normalized");
CREATE INDEX IF NOT EXISTS "idx_drug_recall_recall__882f98" ON "drug_recalls" ("recall_command_date");
CREATE INDEX IF NOT EXISTS "idx_drug_recall_product_ec7e6c" ON "drug_recalls" ("product_name");
CREATE INDEX IF NOT EXISTS "idx_drug_recall_item_se_afe68a" ON "drug_recalls" ("item_seq");
COMMENT ON COLUMN "drug_recalls"."item_seq" IS 'Drug product code (matches medicine_info.item_seq, loose join)';
COMMENT ON COLUMN "drug_recalls"."std_code" IS 'Drug standard code (stdrCode)';
COMMENT ON COLUMN "drug_recalls"."product_name" IS 'Recalled product name (prdtName)';
COMMENT ON COLUMN "drug_recalls"."entrps_name" IS 'Manufacturer name (entrpsName) — raw audit copy';
COMMENT ON COLUMN "drug_recalls"."entrps_name_normalized" IS 'Manufacturer name after normalize_company_name (Q2 matching key)';
COMMENT ON COLUMN "drug_recalls"."recall_reason" IS 'Recall reason text (rtrvlResn) — part of composite UNIQUE';
COMMENT ON COLUMN "drug_recalls"."recall_command_date" IS 'Recall command date (recallCommandDate) in YYYYMMDD';
COMMENT ON COLUMN "drug_recalls"."sale_stop_yn" IS 'Sale-stop flag (Y / N)';
COMMENT ON COLUMN "drug_recalls"."is_hospital_only" IS 'Hospital-only formulation flag (keyword filter result)';
COMMENT ON COLUMN "drug_recalls"."is_non_drug" IS 'Non-drug product flag (toothbrush / sanitary pad / etc.)';
COMMENT ON TABLE "drug_recalls" IS 'MFDS recall and sale-stop notices (loose join with medicine_info)';

-- ═══════════════════════════════════════════════════════════════════
-- 스쿼시 접합: 모델로 표현 불가한 raw-SQL 기능
-- 출처 = 구 마이그레이션 8/10/14/18/28/29/30/32. 목표 = Neon 실측과 일치.
-- (halfvec / tsvector+트리거 / GIN / pg_trgm / 부분인덱스 / JSONB 기본값)
-- ═══════════════════════════════════════════════════════════════════

-- 확장 (halfvec / trgm 전제)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- medicine_chunk.embedding: text -> halfvec(3072) (빈 테이블이라 drop+add)
ALTER TABLE "medicine_chunk" DROP COLUMN IF EXISTS "embedding";
ALTER TABLE "medicine_chunk" ADD COLUMN "embedding" halfvec(3072);
COMMENT ON COLUMN "medicine_chunk"."embedding" IS 'pgvector halfvec(3072) - text-embedding-3-large (16-bit float, HNSW 인덱싱 가능)';

-- medicine_chunk.content_tsv + 자동갱신 트리거 + GIN (RRF BM25 source)
ALTER TABLE "medicine_chunk" ADD COLUMN "content_tsv" tsvector;
CREATE OR REPLACE FUNCTION medicine_chunk_tsv_update()
RETURNS trigger AS $$
BEGIN
    NEW.content_tsv := to_tsvector('simple', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_medicine_chunk_tsv ON "medicine_chunk";
CREATE TRIGGER trg_medicine_chunk_tsv
    BEFORE INSERT OR UPDATE OF content ON "medicine_chunk"
    FOR EACH ROW EXECUTE FUNCTION medicine_chunk_tsv_update();
CREATE INDEX "idx_medicine_chunk_content_tsv_gin" ON "medicine_chunk" USING gin ("content_tsv");

-- medicine_chunk 메타 JSONB 컬럼 3종 + GIN (retrieval ?| 필터 가속)
ALTER TABLE "medicine_chunk"
    ADD COLUMN IF NOT EXISTS "ingredients"        jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS "target_conditions"  jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS "target_lifestyle"   jsonb NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX IF NOT EXISTS "idx_medicine_chunk_ingredients_gin" ON "medicine_chunk" USING gin ("ingredients" jsonb_path_ops);
CREATE INDEX IF NOT EXISTS "idx_medicine_chunk_target_conditions_gin" ON "medicine_chunk" USING gin ("target_conditions" jsonb_path_ops);
CREATE INDEX IF NOT EXISTS "idx_medicine_chunk_target_lifestyle_gin" ON "medicine_chunk" USING gin ("target_lifestyle" jsonb_path_ops);

-- interaction_tags: DB 기본값 + GIN
ALTER TABLE "medicine_chunk" ALTER COLUMN "interaction_tags" SET DEFAULT '[]'::jsonb;
CREATE INDEX IF NOT EXISTS "idx_medicine_chunk_tags_gin" ON "medicine_chunk" USING gin ("interaction_tags" jsonb_path_ops);

-- messages.metadata: DB 기본값 + GIN
ALTER TABLE "messages" ALTER COLUMN "metadata" SET DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS "idx_messages_metadata_gin" ON "messages" USING gin ("metadata");

-- ocr_drafts.medicines: DB 기본값
ALTER TABLE "ocr_drafts" ALTER COLUMN "medicines" SET DEFAULT '[]'::jsonb;

-- medicine_info 약품명 trgm GIN (fuzzy 자동완성)
CREATE INDEX IF NOT EXISTS "idx_medicine_info_name_trgm" ON "medicine_info" USING gin ("medicine_name" gin_trgm_ops);
CREATE INDEX IF NOT EXISTS "idx_medicine_info_item_eng_name_trgm" ON "medicine_info" USING gin ("item_eng_name" gin_trgm_ops);

-- ocr_drafts 부분 인덱스 (consumed_at IS NULL = 활성 draft)
CREATE INDEX IF NOT EXISTS "idx_ocr_drafts_dedup" ON "ocr_drafts" ("profile_id", "image_hash") WHERE (consumed_at IS NULL);
CREATE INDEX IF NOT EXISTS "idx_ocr_drafts_profile_active" ON "ocr_drafts" ("profile_id", "created_at" DESC) WHERE (consumed_at IS NULL);

-- drug_recalls: 모델 생성 평문 인덱스를 Neon 실측과 동일한 DESC 로 교체(최근 회수일자 정렬 가속)
DROP INDEX IF EXISTS "idx_drug_recall_recall__882f98";
CREATE INDEX IF NOT EXISTS "idx_drug_recalls_command_date" ON "drug_recalls" ("recall_command_date" DESC);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "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"
)
