"""앵커 게이트 단위 테스트 (안정화 구간 S1).

코드 주석의 ``QA-##`` 앵커가 **실재하는 큐 항목**을 가리키는지 검사하는 게이트다.
왜 필요한가: 앵커는 "오류 ↔ 코드 위치" 를 잇는 유일한 사람-작성 연결고리인데,
지금은 아무도 검증하지 않는다. 오타 하나로 연결이 조용히 끊어진다.

⚠️ 이 테스트는 **실제 저장소를 읽지 않는다.** `tmp_path` 에 표본을 만들어 검사한다 —
저장소 상태에 따라 결과가 바뀌면 그건 게이트 테스트가 아니라 저장소 스냅샷이다.
"""

from pathlib import Path

from scripts.check_anchors import find_anchors, find_unknown_anchors, read_known_ids

#: 다른 표본과 겹치지 않는 가짜 ID (헛된 초록 예방 — 실재 ID 를 쓰면 무엇을 세는지 흐려진다).
#:
#: ⚠️ **조각으로 조립하는 이유**: 완성된 형태로 적으면 게이트가 자기 테스트 파일을 스캔해
#: "큐에 없는 앵커" 로 잡는다(실제로 두 번 그렇게 됐다 — 두 번째는 *이 주석 자체*가
#: 리터럴을 설명하느라 적어서였다). 소스에 완성형이 남지 않게 하되, 테스트는 진짜 ID
#: 모양을 그대로 검사한다. 도구가 스캔하는 리터럴을 주석에 적으면 오작동한다(대장 D10).
GHOST_ID = "QA-" + "9931"


# ── 앵커 수집 ─────────────────────────────────────────────────────────
# 흐름: 임시 소스 트리 생성 -> 스캔 -> ID 별 위치 목록
def test_find_anchors_collects_id_and_location(tmp_path: Path) -> None:
    """코드 주석의 `QA-##` 를 파일·줄 단위로 모은다."""
    source = tmp_path / "svc.py"
    source.write_text("x = 1\n# QA-29 유예기간\ny = 2\n", encoding="utf-8")

    anchors = find_anchors(tmp_path)

    assert "QA-29" in anchors
    assert anchors["QA-29"] == [f"{source}:2"]


def test_find_anchors_records_every_occurrence(tmp_path: Path) -> None:
    """같은 ID 가 여러 곳에 있으면 **전부** 모은다 — 하나만 세면 영향 범위를 놓친다."""
    (tmp_path / "a.py").write_text("# QA-29\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("# QA-29\n", encoding="utf-8")

    anchors = find_anchors(tmp_path)

    assert len(anchors["QA-29"]) == 2


def test_find_anchors_skips_non_source_files(tmp_path: Path) -> None:
    """문서·캐시는 앵커 원천이 아니다 — 큐 문서 자신이 잡히면 전부 '알려진 ID' 가 된다."""
    (tmp_path / "notes.md").write_text(f"# {GHOST_ID}\n", encoding="utf-8")

    assert find_anchors(tmp_path) == {}


# ── 큐에서 알려진 ID 읽기 ─────────────────────────────────────────────
# 흐름: 큐 마크다운 -> QA-## 전부 추출 -> 집합
def test_read_known_ids_parses_queue_markdown(tmp_path: Path) -> None:
    """큐 문서에 등장하는 모든 `QA-##` 가 '알려진 ID' 다."""
    queue = tmp_path / "QUEUE.md"
    queue.write_text("| **QA-29** | 단계적 삭제 |\n| **QA-30** | 이름 정정 |\n", encoding="utf-8")

    assert read_known_ids(queue) == {"QA-29", "QA-30"}


def test_read_known_ids_returns_empty_when_queue_missing(tmp_path: Path) -> None:
    """큐가 없으면(=CI) 빈 집합 — 호출자가 '검사 불가' 를 판단한다.

    ⚠️ 여기서 "전부 통과" 를 반환하면 안 된다. 검사 대상이 없다는 사실이
    초록으로 보이는 순간 게이트는 통과 기계가 된다.
    """
    assert read_known_ids(tmp_path / "없는파일.md") == set()


# ── 대조 ──────────────────────────────────────────────────────────────
# 흐름: 앵커 - 알려진 ID -> 남은 것이 끊어진 연결
def test_unknown_anchor_is_reported(tmp_path: Path) -> None:
    """큐에 없는 ID 를 코드가 달고 있으면 잡아낸다."""
    anchors = {GHOST_ID: ["app/x.py:3"], "QA-29": ["app/y.py:1"]}

    unknown = find_unknown_anchors(anchors, known={"QA-29"})

    assert list(unknown) == [GHOST_ID]
    assert unknown[GHOST_ID] == ["app/x.py:3"]


def test_all_known_anchors_pass(tmp_path: Path) -> None:
    """전부 실재하면 보고할 것이 없다."""
    assert find_unknown_anchors({"QA-29": ["a.py:1"]}, known={"QA-29", "QA-30"}) == {}
