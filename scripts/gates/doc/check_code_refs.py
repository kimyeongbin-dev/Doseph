r"""코드 참조 게이트 — **문서가 코드 위치를 «줄 번호» 로 가리키는 것**을 막는다.

왜 줄 번호가 나쁜가 — 세 가지가 동시에 나쁘다
---------------------------------------------
**① 조용히 썩는다.** 그 파일을 한 줄만 고쳐도 아래 전부가 밀린다. 문서는 그대로 남고,
**틀렸다는 신호가 없다.** 🔬 실측 2026-09-30: 들여쓰기를 4칸 → 2칸으로 재포맷하니
줄 수가 **-67** 되면서 직하 정본의 인용 **4건**이 다른 코드를 가리켰다.

**② 셀 수가 없다.** 이것이 더 나쁘다. ``_maybe_enqueue_compact`` 를 ``ROADMAP`` 이
*«`:493`·`:585` 2곳 호출»* 이라고 적어 뒀는데, 함수명으로 세어 보니 **5곳**이었다.
🔑 **함수명으로 적으면 ``grep`` 이 다시 셀 수 있어 드리프트가 드러난다 — 줄 번호는 셀 수조차 없다.**

**③ 사람이 못 쓴다.** 줄 번호만 보고는 *«거기에 무엇이 있었나»* 를 알 수 없다.
표식이 ``log_boundary()`` 라면 파일이 바뀌어도 **찾아갈 수 있다.**

⇒ **무엇으로 쓰는가**: 함수·클래스·상수·필드 이름 · ``QA-##`` 같은 ID · 인용할 문자열 자체.

무엇을 보는가 — **살아 있는 문서만**
------------------------------------
| 영역 | 보나 | 왜 |
|---|---|---|
| ``docs-private/`` **직하 정본** | ✅ | 계속 고쳐진다 — 썩으면 다음 사람이 속는다 |
| ``CLAUDE.md`` · 공개 ``docs/`` | ✅ | 같은 이유 |
| ``plan/`` ``record/`` 등 **축 폴더** | ❌ | **닫힌 스냅샷 = 그때의 사실** (FILING §12-1) |
| ``_legacy/`` ``_unfiled/`` | ❌ | 계보가 끊겨 얼어 있다 |
| ``study/`` ``portfolio/`` | ❌ | 🟡 **1차에서는 뺐다** — 좁게 시작해 오탐을 재고 넓힌다 |

🔴 **천장(baseline) 방식이다 — 왜 «0» 이 아닌가**
-------------------------------------------------
착수 시점에 살아 있는 문서에 이미 **53건**이 있었다. 한 번에 다 고치려면 인용마다
*«이 문장이 무엇을 가리키려 했나»* 를 읽고 표식을 골라야 하는데, 서둘러 고치면
**틀린 표식**이 박힌다 — 그건 줄 번호보다 나쁘다(찾아갈 수도, 셀 수도 없다).

⇒ **신규는 즉시 막고, 기존은 줄어들기만 한다.** 이 저장소가 ``mypy`` ·
``coverage`` · ``debt`` 에서 쓰는 방식과 같다. 천장이 내려가면 **손으로 따라 내린다.**

🔴 이 게이트가 **못 하는 것** (한계 선언)
-----------------------------------------
- **표식이 «맞는지» 모른다.** ``log_boundary()`` 라고 적혀 있으면 통과한다 —
  그 함수가 실재하는지, 문맥에 맞는지는 보지 않는다. 그건 사람이 본다.
- **줄 번호가 «옳은지» 도 모른다.** 천장 안이면 통과하므로, 남은 53건 중
  이미 틀린 것이 있어도 조용하다. 밀림 판정은 재포맷 때 따로 쟀다.
- **코드 아닌 인용은 안 본다.** ``.md:12`` · ``.toml:34`` 같은 것은 대상 밖이다.

사용
----
    uv run python -m scripts.gates.doc.check_code_refs
"""

from pathlib import Path
import re
import sys

from scripts.gates._root import PRIVATE, REPO_ROOT

if hasattr(sys.stdout, "reconfigure"):
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
  sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 코드로 볼 확장자. 설정·문서 확장자(`.md`·`.toml`)는 넣지 않는다.
CODE_EXT = "py|js|jsx|ts|tsx|mjs|cjs|sh|sql|css"

#: ``경로.확장자:줄번호``. 🔴 **앵커가 아니라 «확장자 + 콜론 + 숫자» 가 판별자다** —
#: 산문 한가운데에도 오므로 줄머리 앵커를 걸 수 없다.
CITE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:" + CODE_EXT + r"):\d+")

#: 면제 폴더 — **그때의 사실**이거나 얼어 있는 것. 위 표와 같이 읽는다.
EXEMPT_DIRS = frozenset({
  "plan",
  "record",
  "report",
  "architecture",
  "deploy",
  "filing",
  "roadmap",
  "mistake",
  "_legacy",
  "_unfiled",
  "study",
  "portfolio",
})

#: 🔴 천장 — **살아 있는 문서**의 줄 번호 인용 허용 상한.
#:    ⚠️ 실측 2026-09-30: 직하 정본 **41** + `CLAUDE.md`·공개 `docs/` **12** = **53**.
#:    🔑 내려가면 **손으로 따라 내린다.** 올리려면 사유가 필요하다.
CEILING_LIVE = 53

#: 🔑 바닥값 — 면제 영역에서 인용이 **발견되어야** 패턴이 도는 증거가 된다.
#:    0건이면 *"깨끗하다"* 가 아니라 **정규식이 죽었다**는 뜻이다.
#:    ⚠️ 실측 2026-09-30: 축 폴더 101 + `_legacy` 36 + study/portfolio 8 = **145**.
MIN_EXEMPT_HITS = 140


def live_docs() -> list[Path]:
  """줄 번호 인용을 막을 **살아 있는 문서** 목록.

  Returns:
      직하 정본 · ``CLAUDE.md`` · 공개 ``docs/`` 의 ``.md`` 경로들.
  """
  docs = sorted(PRIVATE.glob("*.md"))
  root_claude = REPO_ROOT / "CLAUDE.md"
  if root_claude.is_file():
    docs.append(root_claude)
  public = REPO_ROOT / "docs"
  if public.is_dir():
    docs.extend(sorted(public.rglob("*.md")))
  return docs


def exempt_hits() -> int:
  """면제 영역의 인용 수 — **정규식이 살아 있는지** 재는 대조군.

  Returns:
      면제 폴더에서 찾은 인용 수.
  """
  total = 0
  for path in PRIVATE.rglob("*.md"):
    parts = path.relative_to(PRIVATE).parts
    if not any(part in EXEMPT_DIRS for part in parts):
      continue
    try:
      total += len(CITE.findall(path.read_bytes().decode("utf-8")))
    except (UnicodeDecodeError, OSError):
      continue
  return total


def main() -> int:
  """살아 있는 문서의 줄 번호 인용을 천장과 대조한다.

  Returns:
      종료코드 — 0 이면 통과.
  """
  found: list[tuple[str, str]] = []
  for path in live_docs():
    try:
      text = path.read_bytes().decode("utf-8")
    except (UnicodeDecodeError, OSError):
      continue
    rel = path.relative_to(REPO_ROOT).as_posix()
    found.extend((rel, hit) for hit in CITE.findall(text))

  control = exempt_hits()
  if control < MIN_EXEMPT_HITS:
    print("❌ 코드 참조 검사 실패 — **대조군이 비었다**")
    print(f"   - 면제 영역 인용 {control}건은 바닥값 {MIN_EXEMPT_HITS} 아래다")
    print("   🔑 0건은 «인용이 없다» 가 아니라 «정규식이 죽었다» 다 — 패턴을 먼저 의심한다.")
    return 1

  if len(found) > CEILING_LIVE:
    print(f"❌ 코드 참조 검사 실패 — 살아 있는 문서의 줄 번호 인용 **{len(found)}건** > 천장 {CEILING_LIVE}")
    seen: dict[str, int] = {}
    for rel, _ in found:
      seen[rel] = seen.get(rel, 0) + 1
    for rel, count in sorted(seen.items(), key=lambda row: -row[1])[:10]:
      print(f"   - {rel}  {count}건")
    print()
    print("   🔑 줄 번호는 **조용히 썩고, 셀 수조차 없다.** 파일이 한 줄만 바뀌어도")
    print("      아래 전부가 밀리는데 문서는 그대로 남는다 — 틀렸다는 신호가 없다.")
    print("   ✅ 대신 쓴다: 함수·클래스·상수 이름 · `QA-##` 같은 ID · 인용할 문자열 자체.")
    print("      예) `logger.py:293` → `app/core/logger.py` 의 `log_boundary()`")
    return 1

  print(f"✅ 코드 참조 — 살아 있는 문서 {len(found)}건 ≤ 천장 {CEILING_LIVE} (대조군 {control}건).")
  return 0


if __name__ == "__main__":
  sys.exit(main())
