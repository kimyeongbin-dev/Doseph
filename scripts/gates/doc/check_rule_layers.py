"""**규칙이 발동하는 층에 닿았는지** 센다 — 정본에만 적힌 규칙을 찾아낸다.

규약 정본 = ``docs-private/FILING.md`` §1-1.

왜 이 게이트가 있나
-------------------
규칙을 정본(층 ⑤)에 적으면 **규칙을 세운 것 같은 감각**이 든다. 그런데 ⑤는
**``Read`` 를 부른 순간만** 온다. 행동 규칙을 거기만 두면 **아무도 안 읽고 발동하지 않는다.**

**실측(2026-09-20)**: 하루에 세운 규칙을 손으로 전수 대조하니 **3건이 ⑤에만** 있었다.
그중 둘은 이미 피해가 있었다 —

- ``partial``: 닫는 길이 **5개**가 됐는데 층②의 표는 **4개**만 알고 있었다.
- **mtime 보존 경계**: 층②가 *"보존하라"* 만 말해서 **정본 갱신에까지 넓게 적용**했고,
  그게 대장 **D41**(게이트 신선도 입력 오염)의 원인이었다. *경계 없는 규칙은 넓어진다.*

→ 대장 **D44**. 손으로 찾은 것을 **기계가 대신 찾게** 만든 것이 이 게이트다.

무엇을 검사하나
---------------
1. **FILING 절 ↔ 층②③ 포인터** — 절이 생겼는데 ``CLAUDE.md``·``MEMORY.md`` 어디서도
   ``§N`` 으로 불리지 않으면 보고한다. 면제는 ``rule_layers.toml`` 에 **사유와 함께**.
2. **게이트 훅 ↔ 규칙 정본** — ``.pre-commit-config.yaml`` 이 우리 게이트를 부르는데
   ``docs/QUALITY_GATES.md`` 가 그 **훅 id** 를 모르면 보고한다.
3. 🔴 **게이트 스크립트 ↔ 훅 배선** — 만들어 놓고 안 도는 게이트(**차단**, D12)
4. **ROADMAP 트랙 ↔ MEMORY 라우팅 표** — 트랙 문자가 생겼는데 ③이 라우팅을 모르면 보고한다.

🔴 **이 게이트가 *못* 하는 것 (한계 선언)**
-------------------------------------------
- **"규칙이 세워졌다"를 모른다.** ``FILING.md`` 에 **절이 생기는 것**만 본다.
  규칙을 ``CLAUDE.md`` 에만 세우거나 산문으로 녹이면 **보이지 않는다.**
- **포인터의 내용이 맞는지 모른다.** ``§8-6`` 이라는 글자가 어딘가 있으면 통과한다 —
  그 포인터가 **엉뚱한 설명을 달고 있어도** 잡지 못한다.
- **층③이 "포인터만" 담았는지 모른다.** 내용을 통째로 복사해도 통과한다(그건 사람이 본다).
- 그래서 **차단이 아니라 보고**다. 정밀도가 낮은 검사를 차단으로 만들면 사람이 끈다
  (``docs/QUALITY_GATES.md`` §2-1).

✅ **음성 대조 표본** — 이것들은 **보고되지 않아야** 한다:
  - ``rule_layers.toml`` 에 **사유와 함께** 면제된 절 (판단을 이미 내린 것)
  - 층②·③ 에서 ``§N`` 으로 불리는 절
  - 우리 게이트가 아닌 3rd-party 훅(``ruff``·``eslint``·``check-yaml`` …)

⚠️ ``pre-push`` **로컬 전용**이다. 대상이 없으면 **실패**한다(fail-closed).
"""

from pathlib import Path
import re
import sys
import tomllib

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
# 🔴 stdout 과 stderr 는 **서로를 보호하지 않는다** — 한쪽만 고정하면 다른 쪽이 크래시한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import PRIVATE, REPO_ROOT

EXEMPT_FILE = Path(__file__).with_name("rule_layers.toml")
MEMORY_INDEX = Path.home() / ".claude" / "projects" / "E--Project-Personal-Project-Doseph" / "memory" / "MEMORY.md"

#: ``## 8-6. 제목`` / ``### 12-1. 제목`` 형태의 절 머리.
SECTION = re.compile(r"^#{2,3}\s+(\d+(?:-\d+)?)\.\s+(.+)$", re.MULTILINE)
#: 훅 하나의 블록에서 id 와 본문을 뽑는다.
HOOK = re.compile(r"- id:\s*(\S+)(.*?)(?=\n      - id:|\Z)", re.DOTALL)
#: 그 훅이 **우리 게이트**를 부르는가 (3rd-party 훅은 대상이 아니다).
OURS = re.compile(r"scripts\.gates\.[\w.]+|scripts/[\w/]+\.py")
#: ``## 트랙 D — …``
TRACK = re.compile(r"^##\s+트랙\s+([A-Z])\b", re.MULTILINE)

#: 바닥값 — *0건*만이 아니라 **줄어든 것도 실패**다(D31).
#: 이 값은 **손으로 올린다** — 대상이 늘면 그때 올리는 것이 의식적인 결정이 된다.
MIN_SECTIONS = 25
MIN_HOOKS = 10
MIN_SCRIPTS = 11
MIN_TRACKS = 3


# ── ① FILING 절이 층②③ 에서 불리는가 ────────────────────────────────
# 흐름: FILING 절 수집 -> 면제 목록 제외 -> CLAUDE.md·MEMORY.md 에서 `§N` 검색
def audit_sections(exempt: dict[str, str]) -> tuple[list[str], int]:
    """(고아 절 보고줄, 검사한 절 수)."""
    filing = (PRIVATE / "FILING.md").read_text(encoding="utf-8", errors="replace")
    layer2 = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8", errors="replace")
    layer3 = MEMORY_INDEX.read_text(encoding="utf-8", errors="replace") if MEMORY_INDEX.exists() else ""
    referenced = layer2 + layer3

    reports: list[str] = []
    sections = SECTION.findall(filing)
    for number, title in sections:
        if number in exempt:
            continue
        if not re.search(rf"§\s?{re.escape(number)}\b", referenced):
            clean = re.sub(r"[*`🔴🔑⭐⚠️]", "", title).strip()
            reports.append(
                f"FILING §{number} ({clean[:44]}) — 층②·③ 어디서도 불리지 않는다. "
                "행동 규칙이면 `CLAUDE.md`, 좌표면 `MEMORY.md`. "
                "아니면 `rule_layers.toml` 에 **사유와 함께** 면제",
            )
    return reports, len(sections)


# ── ② 우리 게이트가 규칙 정본에 등재됐는가 ──────────────────────────
# 흐름: .pre-commit-config 의 훅 중 우리 스크립트를 부르는 것만 추림
#       -> QUALITY_GATES.md 가 그 **훅 id** 를 아는가
#       ⚠️ 스크립트 파일명이 아니라 **훅 id** 로 센다 — 정본이 그 이름을 쓴다(대장 D43).
def audit_hooks() -> tuple[list[str], int]:
    """(미등재 훅 보고줄, 검사한 훅 수)."""
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8", errors="replace")
    canon = (REPO_ROOT / "docs" / "QUALITY_GATES.md").read_text(encoding="utf-8", errors="replace")

    reports: list[str] = []
    ours = 0
    for hook_id, body in HOOK.findall(config):
        if not OURS.search(body):
            continue
        ours += 1
        if f"`{hook_id}`" not in canon:
            reports.append(
                f"훅 `{hook_id}` 가 `docs/QUALITY_GATES.md` 에 없다 — "
                "게이트를 만들고 규칙 정본에 등재하지 않았다(D44 와 같은 형태)",
            )
    return reports, ours


# ── ③ ROADMAP 트랙 ↔ MEMORY 라우팅 표 ───────────────────────────────
def audit_tracks() -> tuple[list[str], int]:
    """(라우팅 표가 모르는 트랙 보고줄, 검사한 트랙 수).

    ⚠️ **매칭을 ``ID 패턴``으로 잡는다.** 처음엔 *"라우팅 줄에 그 글자가 있나"* 로 봤는데,
    설명 문구(*"트랙 A제품 / B정리·강화 / C기타 / D재아키텍처"*)에서 글자를 주워
    **``D-N`` 을 지워도 통과**했다 — 결핍 주입에서 드러났다.
    새 세션이 실제로 묻는 것은 *"``D-1`` 을 보면 어디를 여나"* 이므로
    **``<문자>-N`` 형태가 라우팅 표에 있는지**를 본다.
    """
    roadmap = (PRIVATE / "ROADMAP.md").read_text(encoding="utf-8", errors="replace")
    layer3 = MEMORY_INDEX.read_text(encoding="utf-8", errors="replace") if MEMORY_INDEX.exists() else ""
    letters = sorted(set(TRACK.findall(roadmap)))
    reports = [
        f"`ROADMAP.md` 에 트랙 {letter} 가 있는데 `MEMORY.md` 라우팅 표가 `{letter}-N` 을 모른다 — "
        f"새 세션이 `{letter}-1` 을 보고 어느 문서를 열지 못 정한다"
        for letter in letters
        if not re.search(rf"`{letter}-N`|`{letter}-\d+`", layer3)
    ]
    return reports, len(letters)


# ── ④ 게이트 스크립트 ↔ 훅 배선 ────────────────────────────────────
# 흐름: scripts/gates/*/check_*.py 수집 -> .pre-commit-config 가 그 모듈을 부르는가
# 왜: **게이트를 만들었다는 것과 그것이 돈다는 것은 다른 사실이다**(대장 D12 — 훅 미설치로
#     로컬 게이트가 통째로 안 돌던 전례). 배선이 없으면 파일만 있고 **아무 일도 하지 않는다.**
#     이건 정밀도가 100% 라(모듈 경로 문자열 일치) **보고가 아니라 차단**이다.
def audit_wiring() -> tuple[list[str], int]:
    """(배선 안 된 게이트 보고줄, 검사한 스크립트 수)."""
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8", errors="replace")
    scripts = sorted((REPO_ROOT / "scripts" / "gates").glob("*/check_*.py"))
    reports = [
        f"게이트 `{s.relative_to(REPO_ROOT).as_posix()}` 가 `.pre-commit-config.yaml` 에 배선되지 않았다 — "
        "파일만 있고 **돌지 않는다**(대장 D12)"
        for s in scripts
        if f"scripts.gates.{s.parent.name}.{s.stem}" not in config
    ]
    return reports, len(scripts)


def main() -> int:
    """pre-push 훅 진입점.

    Returns:
        0 (보고 전용). 구조가 깨져 **검사하지 못한** 경우에만 1.
    """
    if not (PRIVATE / "FILING.md").exists() or not EXEMPT_FILE.exists():
        print("[거부] 규약 정본 또는 면제 목록을 찾지 못했다 — 검사하지 못했다(fail-closed).", file=sys.stderr)
        return 1

    raw = tomllib.loads(EXEMPT_FILE.read_text(encoding="utf-8"))
    exempt: dict[str, str] = {}
    for item in raw.get("exempt", []):
        if not item.get("reason"):
            print(f"[거부] 면제에 사유가 없다 — §{item.get('section')}", file=sys.stderr)
            print("  사유를 못 쓰겠으면 그건 진짜 구멍이다(fail-closed).", file=sys.stderr)
            return 1
        exempt[str(item["section"])] = item["reason"]

    section_reports, sections_seen = audit_sections(exempt)
    hook_reports, hooks_seen = audit_hooks()
    track_reports, tracks_seen = audit_tracks()
    wiring_reports, scripts_seen = audit_wiring()

    # 🔴 대상이 줄면 "구멍이 없다" 가 아니라 "아무것도 못 봤다" 이다.
    if sections_seen < MIN_SECTIONS or hooks_seen < MIN_HOOKS or scripts_seen < MIN_SCRIPTS or tracks_seen < MIN_TRACKS:
        print(
            f"[거부] 대상이 줄었다 — FILING 절 {sections_seen}(≥{MIN_SECTIONS}) · "
            f"우리 훅 {hooks_seen}(≥{MIN_HOOKS}) · 게이트 스크립트 {scripts_seen}(≥{MIN_SCRIPTS}) · "
            f"트랙 {tracks_seen}(≥{MIN_TRACKS}).",
            file=sys.stderr,
        )
        print("  머리말 모양·훅 배선·경로가 바뀌었다. 줄어든 것도 실패다(fail-closed, D31).", file=sys.stderr)
        return 1

    # 🔴 배선 누락은 **차단**이다 — 정밀도 100%(모듈 경로 문자열 일치)이고, 방치하면
    #    "게이트가 있다" 고 믿으면서 아무것도 안 도는 상태가 된다(D12).
    if wiring_reports:
        print("[거부] 게이트가 배선되지 않았다 — 만든 것과 도는 것은 다른 사실이다\n", file=sys.stderr)
        for line in wiring_reports:
            print(f"  - {line}", file=sys.stderr)
        print(
            "\n  `.pre-commit-config.yaml` 에 훅을 추가하고 "
            "`pre-commit run <id> --hook-stage pre-push` 로 눈으로 확인하라.\n",
            file=sys.stderr,
        )
        return 1

    reports = section_reports + hook_reports + track_reports
    if not reports:
        print(
            f"✅ 규칙↔층 연결 — FILING 절 {sections_seen}(면제 {len(exempt)}) · 우리 훅 {hooks_seen} · "
            f"게이트 스크립트 {scripts_seen}(배선 누락 0) · 트랙 {tracks_seen} · 끊긴 연결 0.",
        )
        return 0

    print(f"🟡 규칙↔층 연결 보고 {len(reports)}건 (차단 아님):")
    for line in reports:
        print(f"   - {line}")
    print(
        "\n   ⚠️ 이 게이트는 **절이 생긴 것**만 본다. 규칙을 산문으로 녹이면 보이지 않는다 —\n"
        "      *보고 0* 이 *규칙이 전부 연결됐다* 는 뜻은 아니다(FILING §1-1).",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
