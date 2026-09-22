"""예방 열 게이트 단위 테스트 (트랙 B-13 S4).

⚠️ `tmp_path` 표본만 쓴다 — 저장소 상태에 따라 결과가 바뀌면 그건 게이트 테스트가 아니라
저장소 스냅샷이다.

🔴 **여기서 잡아야 할 가장 조용한 구멍**: 은퇴한 훅 id 가 `.pre-commit-config.yaml` 의
**주석에 글자로** 남아 있다(실측: `canon-sync` 2곳). `substring` 으로 짜면 **통과한다.**
"""

from pathlib import Path

from scripts.gates.doc.check_mistake_prevention import (
    Known,
    parse_hook_ids,
    verify_reference,
)

CONFIG_WITH_RETIRED_COMMENT = """\
repos:
  - repo: local
    hooks:
      - id: doc-meta
        name: doc-meta
      # ⛔ 은퇴 2026-09-16 — canon-sync (scripts/check_canon_sync.py)
      - id: rule-layers
        name: rule-layers
"""


def make_known(tmp_path: Path) -> Known:
    """표본 저장소로 `Known` 을 만든다.

    Args:
        tmp_path: pytest 임시 디렉터리.

    Returns:
        훅·Ruff·루트가 채워진 `Known`.
    """
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "live.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "GUIDE.md").write_text("intro\n<!-- rule:있는앵커 -->\n규칙 본문\n", encoding="utf-8")
    return Known(
        hooks=frozenset({"doc-meta", "rule-layers"}),
        ruff=frozenset({"BLE", "ANN"}),
        root=tmp_path,
    )


# ── 훅 id 수집 ────────────────────────────────────────────────────────
# 흐름: 설정 본문 -> 줄머리 `- id:` 만 -> 주석 속 이름은 제외
def test_hook_ids_are_read_from_line_anchors_only() -> None:
    """🔴 **주석에 남은 은퇴 훅 이름을 주워 오면 안 된다** — 그러면 죽은 참조가 통과한다."""
    ids = parse_hook_ids(CONFIG_WITH_RETIRED_COMMENT)

    assert ids == {"doc-meta", "rule-layers"}
    assert "canon-sync" not in ids


# ── 참조 디스패치 ─────────────────────────────────────────────────────
# 흐름: 종류 접두사 -> 각각 다른 실재 검증
def test_hook_reference_resolves(tmp_path: Path) -> None:
    """`훅:` 은 설정의 id 목록에 있어야 한다."""
    assert verify_reference("훅:doc-meta", make_known(tmp_path)) is None


def test_retired_hook_reference_is_rejected(tmp_path: Path) -> None:
    """🔴 은퇴한 훅을 가리키면 **막는다** — «막힌다고 적혀 있는데 안 막히는» 상태다."""
    assert verify_reference("훅:canon-sync", make_known(tmp_path)) is not None


def test_ruff_rule_reference_resolves(tmp_path: Path) -> None:
    """`규칙:` 은 `select` 가 켠 규칙군에 속해야 한다."""
    assert verify_reference("규칙:BLE001", make_known(tmp_path)) is None


def test_ruff_rule_outside_select_is_rejected(tmp_path: Path) -> None:
    """켜지지 않은 규칙은 **아무것도 안 막는다.**"""
    assert verify_reference("규칙:PLR0915", make_known(tmp_path)) is not None


def test_script_reference_resolves(tmp_path: Path) -> None:
    """`스크립트:` 는 파일이 실재해야 한다."""
    assert verify_reference("스크립트:scripts/live.py", make_known(tmp_path)) is None


def test_missing_script_is_rejected(tmp_path: Path) -> None:
    """없는 파일을 가리키면 막는다."""
    assert verify_reference("스크립트:scripts/gone.py", make_known(tmp_path)) is not None


def test_doc_anchor_resolves(tmp_path: Path) -> None:
    """`문서:` 는 **앵커 주석**이 그 파일에 있어야 한다 — 절 번호 문자열이 아니다."""
    assert verify_reference("문서:GUIDE.md#있는앵커", make_known(tmp_path)) is None


def test_missing_anchor_is_rejected(tmp_path: Path) -> None:
    """🔴 파일은 있는데 앵커가 없으면 **읽어도 아무것도 안 나오는 주소**다."""
    assert verify_reference("문서:GUIDE.md#없는앵커", make_known(tmp_path)) is not None


def test_unknown_kind_is_rejected(tmp_path: Path) -> None:
    """모르는 종류 접두사는 막는다 — 어휘를 조용히 넓히지 않는다."""
    assert verify_reference("무언가:something", make_known(tmp_path)) is not None
