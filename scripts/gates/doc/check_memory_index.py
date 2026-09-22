"""에이전트 메모리 인덱스(MEMORY.md) ↔ 개별 메모리 파일 정합 검사.

**왜 이 검사가 있나** (2026-09-15 규명):

`MEMORY.md` 인덱스 줄 **4건**이 본문보다 낡아 있었다. 본문은 *"✅ 해결됨"* 인데
인덱스는 *"수정 PLAN 대기"*, 본문은 *"배포 완료"* 인데 인덱스는 *"pending deploy"* 였다.

근본 원인은 **읽기 비대칭 + 사본**이다:

    인덱스(MEMORY.md)  : 매 세션 **전부** 로드된다   ← 낡은 쪽
    개별 메모리 본문    : **회상될 때만** 온다        ← 맞는 쪽

즉 **틀린 사본이 항상 읽히고, 맞는 원본은 거의 안 읽힌다.** 자기교정 기회가
구조적으로 없다. D30(규칙이 사는 층) 과 같은 형태의 실패다.

⚠️ 메모리는 저장소 밖(`~/.claude/projects/...`)에 있다. 그래도 **없으면 실패**한다 —
이 훅은 `pre-push` **로컬 전용**이라 CI 에서 돌지 않으므로 *"없는 환경"* 이 존재하지 않는다.
**검사 대상이 없는 것과 문제가 없는 것은 다르다**(fail-closed).

## 무엇이 게이트이고 무엇이 보고인가

| 검사 | 정밀도 | 취급 |
|---|---|---|
| dangling — 인덱스가 없는 파일을 가리킨다 | 파일 실재 여부(이분법) | 🔴 **실패** |
| orphan — 파일이 인덱스에 없다 | 파일 실재 여부(이분법) | 🔴 **실패** |
| 상태어 충돌 — 본문 `description` 과 인덱스가 반대말 | **실측 2/4 (50%)** | 🟡 **보고만** |

상태어 충돌을 게이트로 만들지 않는 이유: 오늘의 4건 중 2건만 잡힌다.
나머지 2건은 본문 `description` 자체가 상태를 말하지 않아 대조할 것이 없었다.
80% 미만은 게이트가 아니라 보고다 — `docs/QUALITY_GATES.md` §2-1.

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - 인덱스 줄과 파일이 1:1 로 맞는 정상 항목
  - 아직 없는 메모리를 가리키는 ``[[위키링크]]`` 가 **본문에** 있는 경우
    (링크는 "앞으로 쓸 것"을 표시할 수 있다 — 인덱스 항목만 dangling 으로 본다)
"""

from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MEMORY_DIR = Path.home() / ".claude" / "projects" / "E--Project-Personal-Project-Doseph" / "memory"
INDEX = MEMORY_DIR / "MEMORY.md"

#: 바닥값 — *0건*만이 아니라 **줄어든 것도 실패**다(`CLAUDE.md` §6-1, 대장 D31).
#: 실제로 `check_utf8_guard` 가 대상 11건 → 1건이 되고도 초록을 냈다.
#: 이 값은 **손으로 올린다** — 대상이 늘면 그때 올리는 것이 의식적인 결정이 된다.
MIN_MEMORIES = 35

LINK = re.compile(r"\[[^\]]+\]\(([a-z0-9-]+\.md)\)")
DESCRIPTION = re.compile(r"^description:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)

# 서로 반대말인 상태 어휘. 한쪽에만 나오면 인덱스가 낡았을 가능성이 있다.
DONE_WORDS = ("해결됨", "완료", "✅", "해소")
PENDING_WORDS = ("대기", "pending", "미착수", "다음은", "진행 예정", "예정")


# ── 인덱스 줄 수집 ──────────────────────────────────────────────────────
# 흐름: MEMORY.md 의 **모든 줄**에서 메모리 링크를 찾아 {파일명: 그 줄} 로 모은다
# ⚠️ 처음엔 `- [` 목록 항목만 봤는데, 상단 상시규칙 배너(`> 🧹 ... [정책](x.md)`)에서
#    링크된 파일이 orphan 으로 잘못 걸렸다. **도달 가능성**이 기준이지 서식이 아니다.
def index_entries() -> dict[str, str]:
    """메모리 인덱스에서 (파일명 -> 설명) 쌍을 긁어낸다."""
    entries: dict[str, str] = {}
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        for match in LINK.finditer(line):
            entries.setdefault(match.group(1), line.strip())
    return entries


# ── 검사 본문 ───────────────────────────────────────────────────────────
# 흐름: 인덱스 수집 -> dangling/orphan(실패) -> 상태어 충돌(보고)
def main() -> int:
    """인덱스와 실제 메모리 파일을 대조하고 결과를 인쇄한다."""
    # fail-closed: 인덱스를 못 찾으면 "정합하다"가 아니라 "검사하지 못했다"이다.
    # 이 훅은 pre-push 로컬 전용이라 메모리가 없을 이유가 없다.
    if not INDEX.exists():
        print(f"❌ 메모리 인덱스가 없다 — {INDEX}")
        print("   경로가 바뀌었거나 메모리가 사라졌다. 검사가 무력화된 상태다(fail-closed).")
        return 1

    entries = index_entries()
    if not entries:
        print("❌ 인덱스에서 메모리 줄을 한 건도 못 읽었다. 형식이 바뀌었거나 파서가 깨졌다.")
        return 1

    files = {p.name for p in MEMORY_DIR.glob("*.md")} - {"MEMORY.md"}

    dangling = sorted(name for name in entries if name not in files)
    orphan = sorted(files - set(entries))

    conflicts: list[str] = []
    for name, line in sorted(entries.items()):
        if name not in files:
            continue
        body = (MEMORY_DIR / name).read_text(encoding="utf-8")
        found = DESCRIPTION.search(body)
        if not found:
            continue
        description = found.group(1)
        body_done = any(w in description for w in DONE_WORDS)
        index_pending = any(w in line for w in PENDING_WORDS)
        index_done = any(w in line for w in DONE_WORDS)
        if body_done and index_pending and not index_done:
            conflicts.append(f"{name}\n      본문 : {description[:90]}\n      인덱스: {line[:90]}")

    if conflicts:
        print(f"🟡 상태어 충돌 {len(conflicts)}건 — 인덱스가 본문보다 낡았을 수 있다 (보고, 차단 아님):")
        for item in conflicts:
            print(f"   - {item}")
        print()

    failed = False
    if dangling:
        print(f"❌ 인덱스가 **없는 파일**을 가리킨다 {len(dangling)}건:")
        for name in dangling:
            print(f"   - {name}")
        failed = True
    if orphan:
        print(f"❌ 인덱스에 **없는 메모리 파일** {len(orphan)}건 (회상되지 않으면 영원히 안 읽힌다):")
        for name in orphan:
            print(f"   - {name}")
        failed = True

    if failed:
        return 1

    if len(entries) < MIN_MEMORIES or len(files) < MIN_MEMORIES:
        print(
            f"❌ 대상이 줄었다 — 인덱스 항목 {len(entries)}건 · 파일 {len(files)}건 (기대 각 ≥{MIN_MEMORIES}).",
            file=sys.stderr,
        )
        print("   메모리를 대량 삭제했거나 파싱이 깨졌다. 줄어든 것도 실패다(fail-closed).", file=sys.stderr)
        return 1
    print(f"✅ 메모리 인덱스 정합 — 항목 {len(entries)}건 · 파일 {len(files)}건 · dangling 0 · orphan 0.")
    if not conflicts:
        print("   (상태어 충돌도 없음. 단 이 검사는 실측 검출률 50% 라 '깨끗함'의 증거가 아니다.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
