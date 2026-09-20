"""포트폴리오 문서가 근거보다 낡았는지 추적한다.

**왜 이 검사가 있나** (2026-09-15):

`2026-09-08_doseph-security-posture-portfolio.md` 가 **끝난 일 5건을 "진행 예정" 으로 소개**하고 있었다
(CSP·WAF·CI 보안게이트·의심입력 로깅·로깅 정비 — 전부 완료 상태였다).
포트폴리오 문서에서 이건 틀린 정보일 뿐 아니라 **자기 성과를 깎아먹는다.**

포트폴리오 문서는 **저장소의 사실을 빌려다 쓴다.** 원본이 바뀌면 조용히 낡는데,
그 낡음을 알려 주는 장치가 없었다.

## 무엇을 차단하고 무엇을 보고만 하나

| 검사 | 성격 | 취급 |
|---|---|---|
| `portfolio-sync` 블록 자체가 없다 | 규약 위반(이분법) | 🔴 **실패** |
| `sources` 가 **없는 경로**를 가리킨다 | 파일 실재 여부(이분법) | 🔴 **실패** |
| `sync` 필드가 **없다** | 규약 위반 — 없으면 아래 검사가 조용히 건너뛰어진다 | 🔴 **실패**(fail-closed) |
| `sync: draft` | 아직 완료 아님 | 🟡 **보고** — 끝날 때까지 매번 |
| `sources` 중 하나가 `baseline` 보다 새롭다 | 동기화 필요 신호 | 🟡 **보고** |

## 왜 `status` 가 아니라 `sync` 인가 (2026-09-16 개명)

`status` 라는 이름을 **두 가지 다른 뜻**으로 쓰고 있었다:

* `plan` 의 `status` = **생애주기** — 어디 있고 어떻게 닫혔나(`draft`·`active`·`done`·`suspended`…)
* 포트폴리오의 `status` = **근거와 동기화됐나**(`draft`·`synced`)

같은 이름의 다른 필드는 게이트가 `kind` 를 먼저 읽어야만 해석되고, 사람은 매번 헷갈린다.
포트폴리오 쪽은 애초에 `baseline`·`sources` 와 한 묶음인 **동기화 개념**이므로 `sync` 로 바꿨다.
→ 이제 `status` 는 저장소 전체에서 **생애주기 하나만** 뜻한다.

**뒤의 둘을 차단하지 않는 이유**: 근거 문서는 자주 바뀐다. 차단하면 관계없는 작업이
막히고, 그러면 사람이 게이트를 끈다 — 옆의 정확한 검사까지 죽는다
(`docs/QUALITY_GATES.md` §2-1).

⚠️ `docs-private/` 는 git 밖이지만 이 훅은 `pre-push` **로컬 전용**이라 CI 에서 돌지 않는다.
→ 폴더가 없거나 대상이 0건이면 **실패**한다(fail-closed).

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - ``sync: draft`` (🟡 보고이지 차단이 아니다 — 차단하면 작업이 막힌다)
  - 근거가 ``baseline`` 보다 새로운 상태 (역시 보고. *"고쳐야 한다"* 는 사람이 판단한다)
"""

from datetime import UTC, date, datetime
from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import REPO_ROOT  # noqa: E402

#: 바닥값 — *0건*만이 아니라 **줄어든 것도 실패**다(`CLAUDE.md` §6-1, 대장 D31).
#: 실제로 `check_utf8_guard` 가 대상 11건 → 1건이 되고도 초록을 냈다.
#: 이 값은 **손으로 올린다** — 대상이 늘면 그때 올리는 것이 의식적인 결정이 된다.
MIN_PORTFOLIO = 3

PORTFOLIO_DIR = REPO_ROOT / "docs-private" / "portfolio"

BLOCK = re.compile(r"<!--\s*portfolio-sync\s*(.*?)-->", re.DOTALL)
FIELD = re.compile(r"^(sync|baseline|note):\s*(.+?)\s*$", re.MULTILINE)

#: `sync` 가 가질 수 있는 값. 오타가 조용히 "draft 아님"으로 통과하는 것을 막는다.
SYNC_VALUES = frozenset({"draft", "synced"})
SOURCE = re.compile(r"^\s*-\s*(\S+)\s*$", re.MULTILINE)

EXCLUDE = {"README.md"}


# ── 문서 하나의 동기화 상태 판정 ────────────────────────────────────────
# 흐름: portfolio-sync 블록 파싱 -> sync/baseline/sources 추출
#       -> source 실재·mtime 을 baseline 과 비교
def inspect(path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for one portfolio document."""
    text = path.read_text(encoding="utf-8")
    name = path.name
    found = BLOCK.search(text)
    if not found:
        return ([f"{name}: `portfolio-sync` 블록이 없다 (portfolio/README.md 규약)"], [])

    body = found.group(1)
    fields = dict(FIELD.findall(body))
    sources = SOURCE.findall(body)

    errors: list[str] = []
    warnings: list[str] = []

    raw_baseline = fields.get("baseline", "")
    try:
        baseline = date.fromisoformat(raw_baseline)
    except ValueError:
        return ([f"{name}: baseline 이 `YYYY-MM-DD` 가 아니다 ({raw_baseline!r})"], [])

    if not sources:
        errors.append(f"{name}: `sources` 가 비어 있다 — 무엇을 근거로 쓴 문서인지 적어야 추적된다")

    stale: list[str] = []
    for source in sources:
        target = REPO_ROOT / source
        if not target.exists():
            errors.append(f"{name}: sources 가 없는 경로를 가리킨다 → {source}")
            continue
        # aware datetime -> 로컬 날짜. baseline 이 로컬 기준 날짜라 맞춰야 하루가 어긋나지 않는다.
        changed = datetime.fromtimestamp(target.stat().st_mtime, tz=UTC).astimezone().date()
        if changed > baseline:
            stale.append(f"{source} ({changed})")

    if stale:
        warnings.append(
            f"{name}: 근거가 baseline({baseline}) 보다 새롭다 — 동기화 필요\n"
            + "".join(f"        · {s}\n" for s in stale).rstrip(),
        )

    # fail-closed: 필드가 없으면 "draft 가 아니다"가 아니라 "판정하지 못했다"이다.
    # 값이 오타여도 마찬가지 — 조용히 통과하면 게이트가 자기 침묵을 초록으로 보고한다.
    sync = fields.get("sync")
    if sync is None:
        errors.append(f"{name}: `sync` 필드가 없다 — 없으면 draft 검사가 조용히 건너뛰어진다(fail-closed)")
    elif sync not in SYNC_VALUES:
        errors.append(f"{name}: `sync` 값이 {sorted(SYNC_VALUES)} 중 하나가 아니다 ({sync!r})")
    elif sync == "draft":
        note = fields.get("note", "")
        warnings.append(f"{name}: **draft** — 아직 완료된 문서가 아니다" + (f"\n        · {note}" if note else ""))

    return (errors, warnings)


# ── 게이트 본문 ─────────────────────────────────────────────────────────
# 흐름: portfolio/*.md 순회 -> 문서별 판정 -> 오류는 차단, 경고는 보고
def main() -> int:
    # fail-closed: 폴더가 없거나 대상 0건이면 "동기화됐다"가 아니라 "검사하지 못했다"이다.
    if not PORTFOLIO_DIR.exists():
        print(f"❌ 포트폴리오 폴더가 없다 — {PORTFOLIO_DIR}")
        print("   경로 규약이 바뀌었다. 검사가 무력화된 상태다(fail-closed).")
        return 1

    docs = [p for p in sorted(PORTFOLIO_DIR.glob("*.md")) if p.name not in EXCLUDE]
    if not docs:
        print(f"❌ 추적 대상 포트폴리오 문서가 0건이다 — {PORTFOLIO_DIR}")
        print("   전부 옮겨졌거나 glob 이 어긋났다. 검사 대상 0건은 통과가 아니다(fail-closed).")
        return 1

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for doc in docs:
        errors, warnings = inspect(doc)
        all_errors += errors
        all_warnings += warnings

    if all_warnings:
        print(f"🟡 포트폴리오 동기화 보고 {len(all_warnings)}건 (차단 아님):")
        for item in all_warnings:
            print(f"   - {item}")
        print()

    if all_errors:
        print(f"❌ 포트폴리오 규약 위반 {len(all_errors)}건:")
        for item in all_errors:
            print(f"   - {item}")
        return 1

    if len(docs) < MIN_PORTFOLIO:
        print(f"❌ 포트폴리오 문서가 {len(docs)}건이다 (기대 ≥{MIN_PORTFOLIO}) — 경로·glob 이 좁아졌다(fail-closed).")
        return 1
    print(f"✅ 포트폴리오 문서 {len(docs)}건 — 규약 준수 · 없는 근거 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
