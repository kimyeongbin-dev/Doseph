"""`affects` 가 가리키는 «절» 을 어떻게 찾는가 — `section_text()` 단위 테스트.

🔴 **왜 이 테스트가 생겼나** (`문서-36`, 2026-09-27)
`ROADMAP` 트랙 A·B 는 `### B-14` 처럼 **절 제목**을 갖는데 **트랙 C 는 `## 트랙 C` 하나 아래
표 한 줄씩**이다. 그래서 `affects: ROADMAP#C-6` 을 적으면 게이트가
*「`ROADMAP.md` 에 `C-6` 없음」* 으로 **차단**했다 — 실제로 있는 항목인데 가리킬 수 없었다.

⇒ 우회로 `ROADMAP#잔손질`(트랙 C 제목에만 있는 낱말)을 썼는데 **읽는 사람이 왜 그런지 모른다.**
그리고 파급이 있었다: 트랙 C 항목 14개는 **어느 PLAN 도 `affects` 로 가리킬 수 없어**
절 단위 신선도 검사(`FILING` §9-1)가 트랙 C 에 대해 **원리적으로 안 돌았다.**

🔑 **고른 길**: 표제가 없으면 **표 행**을 절로 인정한다. 트랙 C 를 절 14개로 쪼개는 것보다
싸고, `QA-##`·`L-N` 처럼 **표로 사는 다른 원장에도 그대로 이득**이다.

🔴 **앵커가 핵심이다** — 마커는 **행의 첫 칸**에만 있어야 인정한다. 아무 칸이나 보면
산문이 섞이고(`D47`), 그러면 «있다» 가 늘 참이 되어 검사가 죽는다.
"""

from scripts.gates.doc.check_doc_meta import section_text

HEADED = """## 트랙 B — 정리·강화

### B-14 원장 처분

내용 B-14.

### B-15 다음 것

내용 B-15."""

TABLED = """## 트랙 C — 기타 후속 큐

| 항목 | 내용 | 우선 |
|---|---|---|
| **C-1** | Dependabot ESLint 메이저 | 중 |
| **C-6 잔손질** | 원장 = LOCAL_RESIDUE | 낮음 |
| **C-14** | 테스트 커밋이 prod 를 재배포한다 | 낮음 |"""


# ── 음성 대조 — 표제형은 지금까지처럼 동작해야 한다 ──────────────────
def test_heading_section_still_works() -> None:
    """표제로 찾는 기존 동작은 그대로다."""
    found = section_text(HEADED, "B-14")
    assert found is not None
    assert "내용 B-14." in found
    assert "내용 B-15." not in found, "다음 표제에서 멈춰야 한다"


def test_numbered_heading_still_works() -> None:
    """숫자 마커는 `## 5.` · `## §5` 꼴을 찾는다."""
    text = "## 5. 폴더 체계\n\n내용 5.\n\n## 6. 다음\n"
    found = section_text(text, "5")
    assert found is not None
    assert "내용 5." in found
    assert "내용 6." not in found


def test_missing_marker_returns_none() -> None:
    """없는 마커는 `None` — 호출자가 «선언한 절이 실재하지 않는다» 로 판정한다."""
    assert section_text(HEADED, "B-99") is None


# ── 결핍 주입 — 표 행을 절로 인정해야 한다 ──────────────────────────
def test_table_row_is_a_section() -> None:
    """🆕 표제가 없으면 **표 행**을 절로 본다 — 이것이 `문서-36` 의 해소다."""
    found = section_text(TABLED, "C-6")
    assert found is not None, "표 행을 절로 못 찾으면 트랙 C 를 가리킬 수 없다"
    assert "LOCAL_RESIDUE" in found
    assert "Dependabot" not in found, "그 행만 돌려줘야 한다"


def test_table_row_marker_must_be_in_the_first_cell() -> None:
    """🔴 **앵커** — 첫 칸이 아닌 칸의 글자는 마커로 인정하지 않는다(`D47`).

    `재배포` 는 `C-14` 행의 **둘째 칸**에 있다. 이걸 절로 인정하면 산문이 전부 절이 된다.
    """
    assert section_text(TABLED, "재배포") is None


def test_ambiguous_table_marker_is_fail_closed() -> None:
    """같은 마커를 첫 칸에 가진 행이 둘이면 `None` — 어느 쪽인지 모른다."""
    doubled = TABLED + "\n| **C-6 다른 것** | 중복 행 | 낮음 |"
    assert section_text(doubled, "C-6") is None


def test_heading_wins_over_table_row() -> None:
    """표제와 표 행이 둘 다 있으면 **표제**가 이긴다 — 더 큰 단위가 절이다."""
    mixed = HEADED + "\n\n| 항목 | 내용 |\n|---|---|\n| **B-14** | 표 행 쪽 |\n"
    found = section_text(mixed, "B-14")
    assert found is not None
    assert "내용 B-14." in found
    assert "표 행 쪽" not in found
