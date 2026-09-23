"""폴더 색인 게이트 단위 테스트 (트랙 B-14, `문서-14`).

⚠️ `tmp_path` 표본만 쓴다 — 저장소 상태에 따라 결과가 바뀌면 그건 게이트 테스트가 아니라
저장소 스냅샷이다.

🔴 **이 게이트가 존재하는 이유**: 색인은 **처음 오는 사람이 먼저 읽는 자리**인데
**아무 게이트도 안 봤다**(`L-7`). 2026-09-20 개명에서 참조 152회를 고치고도 색인 29줄이
그대로 남아 있었고 게이트는 전부 초록이었다. 새 노트를 만들고 색인을 빠뜨린 것도
**3건 중 3건**이다(`D39`).

🔑 **형식이 셋이다** — `- **이름**` · `` - `이름.md` `` · 표 행 `` | `이름.md` | ``.
형식별 파서를 두지 않고 **«README 가 언급한 이름» ↔ «실물»** 로 비교한다.
"""

from pathlib import Path

from scripts.gates.doc.check_folder_index import IndexReport, audit_folder

SUFFIX = "-study"


def make(tmp_path: Path, readme: str, names: list[str]) -> Path:
    """표본 폴더를 만든다.

    Args:
        tmp_path: pytest 임시 디렉터리.
        readme: `README.md` 본문.
        names: 만들 노트 파일명(확장자 없이).

    Returns:
        만들어진 폴더 경로.
    """
    folder = tmp_path / "study"
    folder.mkdir()
    (folder / "README.md").write_text(readme, encoding="utf-8")
    for name in names:
        (folder / f"{name}.md").write_text("본문\n", encoding="utf-8")
    return folder


def test_all_three_index_formats_are_read(tmp_path: Path) -> None:
    """🔑 굵게·백틱·표 행 **셋 다** 색인 항목으로 읽는다 — 형식이 갈려 있어도 센다."""
    readme = (
        "# 색인\n\n"
        "- **2026-01-01_alpha-study**(요약)\n"
        "- `2026-01-02_beta-study.md`\n"
        "| `2026-01-03_gamma-study.md` | draft |\n"
    )
    folder = make(tmp_path, readme, ["2026-01-01_alpha-study", "2026-01-02_beta-study", "2026-01-03_gamma-study"])

    report = audit_folder(folder, SUFFIX)

    assert report.listed == 3
    assert not report.dangling
    assert not report.orphan


def test_orphan_is_a_file_the_index_forgot(tmp_path: Path) -> None:
    """🔴 새 노트를 만들고 색인을 안 고친 것 — `D39` 가 3건 중 3건 겪은 실패다."""
    folder = make(tmp_path, "- **2026-01-01_alpha-study**\n", ["2026-01-01_alpha-study", "2026-01-09_forgot-study"])

    report = audit_folder(folder, SUFFIX)

    assert report.orphan == ["2026-01-09_forgot-study"]


def test_dangling_is_an_index_entry_with_no_file(tmp_path: Path) -> None:
    """🔴 파일을 옮겼는데 색인은 옛 이름을 부른다 — 찾아 헤매게 만든다."""
    folder = make(tmp_path, "- `2026-01-01_alpha-study.md`\n- `2026-01-02_gone-study.md`\n", ["2026-01-01_alpha-study"])

    report = audit_folder(folder, SUFFIX)

    assert report.dangling == ["2026-01-02_gone-study"]


def test_prose_mention_of_another_folder_is_not_an_entry(tmp_path: Path) -> None:
    """🔑 산문이 **다른 폴더 파일**을 언급해도 색인 항목으로 세지 않는다.

    접미사(`-study`)로 그 폴더 것인지 가른다 — 안 그러면 `DEPLOYMENT.md` 같은 언급이
    전부 dangling 으로 잡혀 **오탐 게이트**가 된다(사람이 끄면 옆의 정확한 게이트까지 죽는다).
    """
    readme = "- **2026-01-01_alpha-study**\n\n정본 = `docs-private/DEPLOYMENT.md` · `FILING.md` 참조\n"
    folder = make(tmp_path, readme, ["2026-01-01_alpha-study"])

    report = audit_folder(folder, SUFFIX)

    assert not report.dangling
    assert not report.orphan


def test_readme_itself_is_not_an_entry(tmp_path: Path) -> None:
    """색인 파일 자신은 항목이 아니다."""
    folder = make(tmp_path, "- **2026-01-01_alpha-study**\n", ["2026-01-01_alpha-study"])

    report = audit_folder(folder, SUFFIX)

    assert report.files == 1


def test_missing_readme_is_fail_closed(tmp_path: Path) -> None:
    """🔴 색인이 아예 없으면 **«어긋남 0» 이 아니라 «못 셌다»** 다."""
    folder = tmp_path / "study"
    folder.mkdir()
    (folder / "2026-01-01_alpha-study.md").write_text("x\n", encoding="utf-8")

    report = audit_folder(folder, SUFFIX)

    assert report.problem is not None


def test_clean_folder_reports_no_problem(tmp_path: Path) -> None:
    """음성 대조 — 맞는 색인은 통과해야 한다."""
    folder = make(tmp_path, "- **2026-01-01_alpha-study**\n", ["2026-01-01_alpha-study"])

    report: IndexReport = audit_folder(folder, SUFFIX)

    assert report.problem is None
    assert not report.dangling
    assert not report.orphan
