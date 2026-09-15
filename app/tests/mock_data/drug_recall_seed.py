"""§14.5 시드 데이터 (2026-04-27 KST 추출).

인계 문서(비공개) 의 §14.5.1 / §14.5.2 / §14.5.4 에서 추출한 raw API row 를 dict 로 임베드.

- ``SEED_RECALL_30``: §14.5.1 — 회수·판매중지 30건.
  * `202007244` 가 3건 / `201904809` 가 2건 — **복합 UNIQUE 검증용**
- ``SEED_MEDICINE_INFO_RECALL_5``: §14.5.2 — 회수 약과 동일 ITEM_SEQ 의 허가 정보 5건.
  모두 ``CANCEL_NAME=정상`` (별도 테이블 분리 정책 검증)
- ``SEED_MEDICINE_INFO_NORMAL_30``: §14.5.4 — 일반약 30건.
  * `정상` 24 / `유효기간만료` 6 — 시딩 시 둘 다 적재

Field naming follows the API response (uppercase) so callers may pass
the dicts straight to `MedicineDataService._transform_item`.
"""

from typing import Any

# ── §14.5.1 회수·판매중지 30건 (totalCount=913 중 최신순) ────────────
# 키 매핑 (식약처 API → 내부 모델):
#     ITEM_SEQ            → item_seq
#     PRDUCT              → product_name
#     ENTRPS              → entrps_name
#     RTRVL_RESN          → recall_reason
#     RECALL_COMMAND_DATE → recall_command_date
#     STDR_CODE           → std_code
#     SALE_STOP_YN        → sale_stop_yn
SEED_RECALL_30: list[dict[str, Any]] = [
    {
        "ITEM_SEQ": "199805821",
        "PRDUCT": "풍산토사자",
        "ENTRPS": "풍산주식회사",
        "RTRVL_RESN": "성상 부적합",
        "RECALL_COMMAND_DATE": "20260422",
    },
    {
        "ITEM_SEQ": "202300562",
        "PRDUCT": "그린파인치약",
        "ENTRPS": "우리생활건강",
        "RTRVL_RESN": "품질부적합 우려(그린파인치약)",
        "RECALL_COMMAND_DATE": "20260422",
    },
    {
        "ITEM_SEQ": "202300984",
        "PRDUCT": "단바이오치약",
        "ENTRPS": "우리생활건강",
        "RTRVL_RESN": "품질부적합 우려",
        "RECALL_COMMAND_DATE": "20260422",
    },
    {
        "ITEM_SEQ": "201206589",
        "PRDUCT": "솔고플라티노이온덴티치약",
        "ENTRPS": "우리생활건강",
        "RTRVL_RESN": "품질부적합 우려",
        "RECALL_COMMAND_DATE": "20260422",
    },
    {
        "ITEM_SEQ": "202007244",
        "PRDUCT": "마데바텔넥치약",
        "ENTRPS": "우리생활건강",
        "RTRVL_RESN": "품질부적합 우려(마데바텔넥치약)",
        "RECALL_COMMAND_DATE": "20260420",
    },
    {
        "ITEM_SEQ": "202007244",
        "PRDUCT": "프로폴리브러쉬치약",
        "ENTRPS": "우리생활건강",
        "RTRVL_RESN": "품질부적합 우려(프로폴리브러쉬치약)",
        "RECALL_COMMAND_DATE": "20260420",
    },
    {
        "ITEM_SEQ": "202007244",
        "PRDUCT": "덴탈힐링프로폴치약",
        "ENTRPS": "우리생활건강",
        "RTRVL_RESN": "품질부적합 우려(덴탈힐링프로폴치약)",
        "RECALL_COMMAND_DATE": "20260420",
    },
    {
        "ITEM_SEQ": "201908485",
        "PRDUCT": "리버만로라부스트액(L-아스파르트산-L-오르니틴)",
        "ENTRPS": "동아제약(주)",
        "RTRVL_RESN": "안정성시험 일부항목(성상)",
        "RECALL_COMMAND_DATE": "20260415",
    },
    {
        "ITEM_SEQ": "200711240",
        "PRDUCT": "농림자소엽",
        "ENTRPS": "(주)농림생약",
        "RTRVL_RESN": "순도시험 1) 이물 가) 줄기",
        "RECALL_COMMAND_DATE": "20260410",
    },
    {
        "ITEM_SEQ": "200504654",
        "PRDUCT": "현진단삼",
        "ENTRPS": "(주)현진제약",
        "RTRVL_RESN": "정량법(살비아놀산 B)",
        "RECALL_COMMAND_DATE": "20260410",
    },
    {
        "ITEM_SEQ": "200302817",
        "PRDUCT": "구미포비스왑스틱(포비돈요오드)",
        "ENTRPS": "구미제약(주)",
        "RTRVL_RESN": "이물 혼입",
        "RECALL_COMMAND_DATE": "20260410",
    },
    {
        "ITEM_SEQ": "201309487",
        "PRDUCT": "이트라펜정",
        "ENTRPS": "(주)화이트생명과학",
        "RTRVL_RESN": "불순물(N-nitroso-desmethyl)",
        "RECALL_COMMAND_DATE": "20260406",
    },
    {
        "ITEM_SEQ": "201906489",
        "PRDUCT": "평위천프라임액",
        "ENTRPS": "광동제약(주)",
        "RTRVL_RESN": "카톤 포장 오류",
        "RECALL_COMMAND_DATE": "20260406",
    },
    {
        "ITEM_SEQ": "201507284",
        "PRDUCT": "제이리브현탁액",
        "ENTRPS": "제이더블유중외제약(주)",
        "RTRVL_RESN": "의약품 동등성 재평가",
        "RECALL_COMMAND_DATE": "20260403",
    },
    {
        "ITEM_SEQ": "200707223",
        "PRDUCT": "엔시트라정",
        "ENTRPS": "한림제약(주)",
        "RTRVL_RESN": "불순물(N-nitroso-desmethyl)",
        "RECALL_COMMAND_DATE": "20260402",
    },
    {
        "ITEM_SEQ": "200109947",
        "PRDUCT": "부광미다졸람주사",
        "ENTRPS": "부광약품(주)",
        "RTRVL_RESN": "2차 포장 표시 오기",
        "RECALL_COMMAND_DATE": "20260402",
    },
    {
        "ITEM_SEQ": "201900333",
        "PRDUCT": "삼성로수바스타틴정20밀리그램",
        "ENTRPS": "삼성제약(주)",
        "RTRVL_RESN": "바코드 오류",
        "RECALL_COMMAND_DATE": "20260401",
    },
    {
        "ITEM_SEQ": "200706110",
        "PRDUCT": "엑스페인정",
        "ENTRPS": "(주)한독",
        "RTRVL_RESN": "니트로사민류 불순물",
        "RECALL_COMMAND_DATE": "20260401",
    },
    {
        "ITEM_SEQ": "200706109",
        "PRDUCT": "엑스페인세미정",
        "ENTRPS": "(주)한독",
        "RTRVL_RESN": "니트로사민류 불순물",
        "RECALL_COMMAND_DATE": "20260401",
    },
    {
        "ITEM_SEQ": "200903973",
        "PRDUCT": "마데카솔케어연고",
        "ENTRPS": "동국제약(주)",
        "RTRVL_RESN": "포장재 불량(코팅 벗겨짐)",
        "RECALL_COMMAND_DATE": "20260401",
    },
    {
        "ITEM_SEQ": "201900582",
        "PRDUCT": "엔탭허브골쇄보",
        "ENTRPS": "(주)엔탭허브",
        "RTRVL_RESN": "성상",
        "RECALL_COMMAND_DATE": "20260331",
    },
    {
        "ITEM_SEQ": "201800362",
        "PRDUCT": "자연세상유백피",
        "ENTRPS": "(주)자연세상",
        "RTRVL_RESN": "성상",
        "RECALL_COMMAND_DATE": "20260331",
    },
    {
        "ITEM_SEQ": "202500553",
        "PRDUCT": "아딘폴거품세정액",
        "ENTRPS": "(주)성원제약",
        "RTRVL_RESN": "품질부적합 우려",
        "RECALL_COMMAND_DATE": "20260331",
    },
    {
        "ITEM_SEQ": "201700189",
        "PRDUCT": "퓨어검덴탈케어치약",
        "ENTRPS": "(주)성원제약",
        "RTRVL_RESN": "품질부적합 우려",
        "RECALL_COMMAND_DATE": "20260331",
    },
    {
        "ITEM_SEQ": "201904809",
        "PRDUCT": "굿모닝미소지은이프레쉬치약",
        "ENTRPS": "(주)성원제약",
        "RTRVL_RESN": "품질부적합 우려",
        "RECALL_COMMAND_DATE": "20260331",
    },
    {
        "ITEM_SEQ": "201904809",
        "PRDUCT": "원투쓰리치약",
        "ENTRPS": "(주)성원제약",
        "RTRVL_RESN": "품질부적합 우려(엔트리구강)",
        "RECALL_COMMAND_DATE": "20260331",
    },
    {
        "ITEM_SEQ": "201203603",
        "PRDUCT": "잇몸케어플러스치약",
        "ENTRPS": "(주)성원제약",
        "RTRVL_RESN": "품질부적합 우려",
        "RECALL_COMMAND_DATE": "20260331",
    },
    {
        "ITEM_SEQ": "200305540",
        "PRDUCT": "뉴키토플러스원치약",
        "ENTRPS": "(주)성원제약",
        "RTRVL_RESN": "품질부적합 우려",
        "RECALL_COMMAND_DATE": "20260331",
    },
    {
        "ITEM_SEQ": "200511279",
        "PRDUCT": "프로토픽연고0.1%(타크로리무스수화물)",
        "ENTRPS": "레오파마(유)",
        "RTRVL_RESN": "2차 포장용기 표시",
        "RECALL_COMMAND_DATE": "20260330",
    },
    {
        "ITEM_SEQ": "200401147",
        "PRDUCT": "프레벨액0.25%(프레드니카르베이트)",
        "ENTRPS": "태극제약(주)",
        "RTRVL_RESN": "직접용기 불량(누설)",
        "RECALL_COMMAND_DATE": "20260330",
    },
]

# ── §14.5.2 Q1 매칭 5건 (회수 약 ITEM_SEQ → 의약품 허가 데이터) ──────
# 결정적 검증 결과: 5건 모두 medicine_info 에는 CANCEL_NAME=정상.
# → drug_recalls 와 medicine_info 는 별도 테이블로 관리해야 함을 입증.
SEED_MEDICINE_INFO_RECALL_5: list[dict[str, Any]] = [
    {"ITEM_SEQ": "200903973", "ITEM_NAME": "마데카솔케어연고", "ENTP_NAME": "동국제약(주)", "CANCEL_NAME": "정상"},
    {"ITEM_SEQ": "201309487", "ITEM_NAME": "이트라펜정", "ENTP_NAME": "(주)화이트생명과학", "CANCEL_NAME": "정상"},
    {"ITEM_SEQ": "200706110", "ITEM_NAME": "엑스페인정", "ENTP_NAME": "(주)한독", "CANCEL_NAME": "정상"},
    {"ITEM_SEQ": "200109947", "ITEM_NAME": "부광미다졸람주사", "ENTP_NAME": "부광약품(주)", "CANCEL_NAME": "정상"},
    {
        "ITEM_SEQ": "201900333",
        "ITEM_NAME": "삼성로수바스타틴정20밀리그램(로수바스타틴)",
        "ENTP_NAME": "삼성제약(주)",
        "CANCEL_NAME": "정상",
    },
]

# ── §14.5.4 의약품 허가 API 일반약 30건 (medicine_info 시드) ──────────
# CANCEL_NAME 분포: `정상` 24건 / `유효기간만료` 6건.
# 두 값 모두 적재 (의약품 DB 컨벤션).
SEED_MEDICINE_INFO_NORMAL_30: list[dict[str, Any]] = [
    {
        "ITEM_SEQ": "201100828",
        "ITEM_NAME": "벨메텍정20밀리그램(올메사르탄메독소밀)",
        "ENTP_NAME": "(주)종근당",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100830",
        "ITEM_NAME": "올사텐정20밀리그램",
        "ENTP_NAME": "국제약품(주)",
        "CANCEL_NAME": "유효기간만료",
    },
    {"ITEM_SEQ": "201100866", "ITEM_NAME": "오메탄정20밀리그램", "ENTP_NAME": "진양제약(주)", "CANCEL_NAME": "정상"},
    {"ITEM_SEQ": "201100867", "ITEM_NAME": "오메탄정10밀리그램", "ENTP_NAME": "진양제약(주)", "CANCEL_NAME": "정상"},
    {
        "ITEM_SEQ": "201100868",
        "ITEM_NAME": "오메탄정40밀리그램",
        "ENTP_NAME": "진양제약(주)",
        "CANCEL_NAME": "유효기간만료",
    },
    {
        "ITEM_SEQ": "201100869",
        "ITEM_NAME": "올스텍정20밀리그램",
        "ENTP_NAME": "(주)팜젠사이언스",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100874",
        "ITEM_NAME": "라이넥주바이알(자하거가수분해물)",
        "ENTP_NAME": "(주)녹십자웰빙",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100879",
        "ITEM_NAME": "칸살탄플러스정16/12.5mg",
        "ENTP_NAME": "영진약품(주)",
        "CANCEL_NAME": "정상",
    },
    {"ITEM_SEQ": "201100887", "ITEM_NAME": "올위너플러스정", "ENTP_NAME": "대화제약(주)", "CANCEL_NAME": "정상"},
    {
        "ITEM_SEQ": "201100888",
        "ITEM_NAME": "올스텍플러스정20/12.5밀리그램",
        "ENTP_NAME": "(주)팜젠사이언스",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100889",
        "ITEM_NAME": "오메탄플러스정20/12.5밀리그램",
        "ENTP_NAME": "진양제약(주)",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100890",
        "ITEM_NAME": "올사텐플러스정20/12.5밀리그램",
        "ENTP_NAME": "국제약품(주)",
        "CANCEL_NAME": "유효기간만료",
    },
    {
        "ITEM_SEQ": "201100892",
        "ITEM_NAME": "제이메텍플러스정20/12.5밀리그램",
        "ENTP_NAME": "(주)비보존제약",
        "CANCEL_NAME": "유효기간만료",
    },
    {
        "ITEM_SEQ": "201100893",
        "ITEM_NAME": "올고탄플러스정20/12.5밀리그램",
        "ENTP_NAME": "일양약품(주)",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100894",
        "ITEM_NAME": "올메히드플러스정20/12.5밀리그램",
        "ENTP_NAME": "(주)다산제약",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100896",
        "ITEM_NAME": "휴메텍정20밀리그램",
        "ENTP_NAME": "한국휴텍스제약(주)",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100898",
        "ITEM_NAME": "이텍스올메사탄정20밀리그램",
        "ENTP_NAME": "(주)테라젠이텍스",
        "CANCEL_NAME": "정상",
    },
    {
        "ITEM_SEQ": "201100899",
        "ITEM_NAME": "대한올메사탄정20밀리그램",
        "ENTP_NAME": "대한약품공업(주)",
        "CANCEL_NAME": "정상",
    },
    {"ITEM_SEQ": "201100901", "ITEM_NAME": "올위너정20밀리그램", "ENTP_NAME": "대화제약(주)", "CANCEL_NAME": "정상"},
    {"ITEM_SEQ": "201100902", "ITEM_NAME": "올메잘탄정20밀리그램", "ENTP_NAME": "(주)일화", "CANCEL_NAME": "정상"},
    {
        "ITEM_SEQ": "201100904",
        "ITEM_NAME": "올탄플러스정20/12.5밀리그램",
        "ENTP_NAME": "유니메드제약(주)",
        "CANCEL_NAME": "정상",
    },
    {"ITEM_SEQ": "201100905", "ITEM_NAME": "올탄정20밀리그램", "ENTP_NAME": "유니메드제약(주)", "CANCEL_NAME": "정상"},
    {"ITEM_SEQ": "201100906", "ITEM_NAME": "올메살탄정20밀리그램", "ENTP_NAME": "영풍제약(주)", "CANCEL_NAME": "정상"},
    {
        "ITEM_SEQ": "201100908",
        "ITEM_NAME": "제뉴원올메사탄정20밀리그램",
        "ENTP_NAME": "주식회사제뉴원사이언스",
        "CANCEL_NAME": "정상",
    },
    {"ITEM_SEQ": "201100909", "ITEM_NAME": "올메산정20밀리그램", "ENTP_NAME": "명문제약(주)", "CANCEL_NAME": "정상"},
    {"ITEM_SEQ": "201100911", "ITEM_NAME": "올메잘탄플러스정", "ENTP_NAME": "(주)일화", "CANCEL_NAME": "정상"},
    {
        "ITEM_SEQ": "201100913",
        "ITEM_NAME": "올메딜정20밀리그램",
        "ENTP_NAME": "(주)메디카코리아",
        "CANCEL_NAME": "정상",
    },
    {"ITEM_SEQ": "201100917", "ITEM_NAME": "위메탄정20밀리그램", "ENTP_NAME": "위더스제약(주)", "CANCEL_NAME": "정상"},
    {
        "ITEM_SEQ": "201100918",
        "ITEM_NAME": "올살탄정20밀리그램",
        "ENTP_NAME": "삼천당제약(주)",
        "CANCEL_NAME": "유효기간만료",
    },
    {
        "ITEM_SEQ": "201100944",
        "ITEM_NAME": "파타딘점안액(올로파타딘염산염)(군납)",
        "ENTP_NAME": "유니메드제약(주)",
        "CANCEL_NAME": "정상",
    },
]

# 5월2일 최종적으로 추가한 실전활용 용도의 recall drug 데이터 20개
# - 활성성분명(라니티딘/발사르탄/메틸프레드니솔론 등)은 실제 명칭.
# - 회사명·제품 브랜드명은 모두 합성. 실재 제약사 명예훼손 회피 + 매칭
#   알고리즘(item_seq / entrps_name_normalized / 복합 UNIQUE) 검증 전용.
# - 분포: NDMA 2 / GMP 동일 제조사 3 / 자율회수 2 / 의약외품 4 /
#         병원전용 2 / 한약재 2 / 포장오류 2 / 동일 ITEM_SEQ x 2 사유 2 /
#         의약품 동등성 재평가 1 = 20건
# - ITEM_SEQ 는 `2025040XX` 대역으로 신규 발급 (기존 SEED_RECALL_30 과 충돌 없음).
SEED_RECALL_PRODUCTION_20: list[dict[str, Any]] = [
    # ── §1 NDMA/NDEA 발암성 불순물 (sale_stop=Y, ⚠️ 강한 알림 분기) ──
    {
        "ITEM_SEQ": "202504001",
        "PRDUCT": "데모라니티딘정150밀리그램",
        "ENTRPS": "(주)데모제약",
        "RTRVL_RESN": (
            "N-니트로소디메틸아민(NDMA) 잠정관리기준(0.32ppm) 초과 검출 — "
            "IARC 2A군 발암 가능성으로 전량 회수 및 판매중지"
        ),
        "RECALL_COMMAND_DATE": "20260428",
        "STDR_CODE": "8800001501010",
        "SALE_STOP_YN": "Y",
    },
    {
        "ITEM_SEQ": "202504002",
        "PRDUCT": "샘플발사르탄정80밀리그램",
        "ENTRPS": "(주)샘플바이오",
        "RTRVL_RESN": ("N-니트로소디에틸아민(NDEA) 검출 — IARC 2A군 발암 가능성. 전량 회수 및 판매중지"),
        "RECALL_COMMAND_DATE": "20260427",
        "STDR_CODE": "8800002080020",
        "SALE_STOP_YN": "Y",
    },
    # ── §2 GMP 위반 동일 제조사 일괄 회수 3품목 (sale_stop=Y, cross-product 매칭) ──
    {
        "ITEM_SEQ": "202504003",
        "PRDUCT": "테스트솔정4밀리그램(메틸프레드니솔론)",
        "ENTRPS": "(주)테스트팜",
        "RTRVL_RESN": ("제조소 GMP 위반 — 무균공정 자료 위·변조 적발. 동일 제조라인 12개 품목 일괄 회수"),
        "RECALL_COMMAND_DATE": "20260425",
        "SALE_STOP_YN": "Y",
    },
    {
        "ITEM_SEQ": "202504004",
        "PRDUCT": "테스트프레드정5밀리그램(프레드니솔론)",
        "ENTRPS": "(주)테스트팜",
        "RTRVL_RESN": "제조소 GMP 위반 — 무균공정 자료 위·변조 적발. 일괄 회수",
        "RECALL_COMMAND_DATE": "20260425",
        "SALE_STOP_YN": "Y",
    },
    {
        "ITEM_SEQ": "202504005",
        "PRDUCT": "테스트덱정0.5밀리그램(덱사메타손)",
        "ENTRPS": "(주)테스트팜",
        "RTRVL_RESN": "제조소 GMP 위반 — 무균공정 자료 위·변조 적발. 일괄 회수",
        "RECALL_COMMAND_DATE": "20260425",
        "SALE_STOP_YN": "Y",
    },
    # ── §3 표시사항 자율회수 (sale_stop=N, 부드러운 안내 분기) ──
    {
        "ITEM_SEQ": "202504006",
        "PRDUCT": "데이오웬크림0.05%(데소나이드)",
        "ENTRPS": "데이약사주식회사",
        "RTRVL_RESN": ("1차 포장(튜브) 표시사항 오기 — 유효성분 함량 표기 오류(0.05% → 0.5%). 자율 회수 권고"),
        "RECALL_COMMAND_DATE": "20260420",
        "SALE_STOP_YN": "N",
    },
    {
        "ITEM_SEQ": "202504007",
        "PRDUCT": "알파아세트아미노펜정500밀리그램",
        "ENTRPS": "(주)알파제약",
        "RTRVL_RESN": "임부 사용 주의 표시 누락 — 자율 회수 권고",
        "RECALL_COMMAND_DATE": "20260418",
        "SALE_STOP_YN": "N",
    },
    # ── §4 의약외품 4건 (is_non_drug=True 분기 — 사용자 알림 노이즈 차단 검증) ──
    {
        "ITEM_SEQ": "202504008",
        "PRDUCT": "베타프레쉬치약",
        "ENTRPS": "베타제약(주)",
        "RTRVL_RESN": "품질부적합 우려 — 자율 회수",
        "RECALL_COMMAND_DATE": "20260415",
        "SALE_STOP_YN": "N",
    },
    {
        "ITEM_SEQ": "202504009",
        "PRDUCT": "감마손소독제500밀리리터",
        "ENTRPS": "(주)감마약품",
        "RTRVL_RESN": "메탄올 함유 — 사용금지 및 회수",
        "RECALL_COMMAND_DATE": "20260414",
        "SALE_STOP_YN": "Y",
    },
    {
        "ITEM_SEQ": "202504010",
        "PRDUCT": "델타민트구강세정액",
        "ENTRPS": "(주)델타바이오",
        "RTRVL_RESN": "표시기재사항 오기 — 자율 회수",
        "RECALL_COMMAND_DATE": "20260412",
        "SALE_STOP_YN": "N",
    },
    {
        "ITEM_SEQ": "202504011",
        "PRDUCT": "엡실론기능성치약",
        "ENTRPS": "(주)엡실론케어",
        "RTRVL_RESN": "품질부적합 우려 — 자율 회수",
        "RECALL_COMMAND_DATE": "20260410",
        "SALE_STOP_YN": "N",
    },
    # ── §5 병원전용 2건 (is_hospital_only=True 분기 — 일반 사용자 매칭 안 됨 검증) ──
    {
        "ITEM_SEQ": "202504012",
        "PRDUCT": "제타미다졸람주사5밀리그램(미다졸람염산염)",
        "ENTRPS": "(주)제타파마",
        "RTRVL_RESN": "2차 포장 표시 오기",
        "RECALL_COMMAND_DATE": "20260408",
        "SALE_STOP_YN": "Y",
    },
    {
        "ITEM_SEQ": "202504013",
        "PRDUCT": "에타세파졸린나트륨주사1그램",
        "ENTRPS": "에타제약(주)",
        "RTRVL_RESN": "엔도톡신 시험 부적합 — 전량 회수",
        "RECALL_COMMAND_DATE": "20260407",
        "SALE_STOP_YN": "Y",
    },
    # ── §6 한약재 2건 (사용자 매칭 안 되는 정상 케이스 — false positive 검증) ──
    {
        "ITEM_SEQ": "202504014",
        "PRDUCT": "이오타황기",
        "ENTRPS": "(주)이오타생약",
        "RTRVL_RESN": "성상 부적합",
        "RECALL_COMMAND_DATE": "20260405",
        "SALE_STOP_YN": "N",
    },
    {
        "ITEM_SEQ": "202504015",
        "PRDUCT": "카파당귀",
        "ENTRPS": "(주)카파한약",
        "RTRVL_RESN": "순도시험 1) 이물 가) 줄기",
        "RECALL_COMMAND_DATE": "20260403",
        "SALE_STOP_YN": "N",
    },
    # ── §7 일반 회수 2건 (낮은 위험, 사용자 약과 무관한 행) ──
    {
        "ITEM_SEQ": "202504016",
        "PRDUCT": "람다스타틴정20밀리그램(아토르바스타틴)",
        "ENTRPS": "(주)람다파마",
        "RTRVL_RESN": "바코드 오류 — 자율 회수",
        "RECALL_COMMAND_DATE": "20260331",
        "SALE_STOP_YN": "N",
    },
    {
        "ITEM_SEQ": "202504017",
        "PRDUCT": "뮤플러스액100밀리리터",
        "ENTRPS": "뮤제약(주)",
        "RTRVL_RESN": "카톤 포장 오류",
        "RECALL_COMMAND_DATE": "20260328",
        "SALE_STOP_YN": "N",
    },
    # ── §8 동일 ITEM_SEQ x 2 사유 (복합 UNIQUE (item_seq, date, reason) 검증) ──
    {
        "ITEM_SEQ": "202504018",
        "PRDUCT": "오미크론케어연고",
        "ENTRPS": "(주)오미크론바이오",
        "RTRVL_RESN": "포장재 불량(코팅 벗겨짐)",
        "RECALL_COMMAND_DATE": "20260326",
        "SALE_STOP_YN": "N",
    },
    {
        "ITEM_SEQ": "202504018",  # 동일 ITEM_SEQ (복합 UNIQUE 두 번째 행)
        "PRDUCT": "오미크론케어연고",
        "ENTRPS": "(주)오미크론바이오",
        "RTRVL_RESN": "안정성시험 일부항목(성상)",
        "RECALL_COMMAND_DATE": "20260326",
        "SALE_STOP_YN": "N",
    },
    # ── §9 의약품 동등성 재평가 1건 (낮은 위험, 안내성 알림) ──
    {
        "ITEM_SEQ": "202504019",
        "PRDUCT": "파이메트포르민정500밀리그램",
        "ENTRPS": "(주)파이팜",
        "RTRVL_RESN": "의약품 동등성 재평가 — 자료 보완 필요로 자율 회수",
        "RECALL_COMMAND_DATE": "20260322",
        "SALE_STOP_YN": "N",
    },
]
