"""공백 위생 게이트 — **줄끝 공백 · 탭 들여쓰기 · 파일 끝 개행**을 한 자리에서 본다.

왜 필요한가 — `trailing-whitespace` 훅과 겹치지 않는다
------------------------------------------------------
`pre-commit-hooks` 의 ``trailing-whitespace`` 와 ``end-of-file-fixer`` 가 이미 있고
**잘 돌고 있다**(실측 2026-09-30: 추적 ``.md`` 33개의 줄끝 공백 **0건**).
그런데 그 훅들은 **staged 파일만** 받는다. gitignore 된 ``docs-private/`` 는
**한 번도 staged 되지 않으므로** 구조적으로 밖에 있다 — `check_line_endings` 와 **같은 구멍**이다.

🔬 실측 2026-09-30: 추적 파일 0건인 상태에서 미추적 문서에 줄끝 공백 **82건**이 있었다.

🔴 **왜 «전수» 가 아니라 «가려서» 보는가**
------------------------------------------
줄끝 공백이 **데이터인 파일이 있다.** 실측으로 확인했다:

- ``backups/*.sql`` — 줄끝 공백 **2,011건**이 전부 DB 에 저장된 HTML 조각 안의 공백이다
  (``'<![CDATA[<tbody> '`` · ``' <tr> '``). 지우면 **데이터가 변한다.**
- ``*.pem`` — 개인키다. 바이트를 건드리지 않는다.
- ``medication-frontend/out/`` — 빌드 산출물이라 다음 빌드가 되돌린다.
- ``.idea/`` — IDE 가 재생성한다.

⇒ **소스·문서 확장자만** 본다. 목록에 없는 확장자는 대상 밖이다.
🔑 `check_line_endings` 는 전수를 보는데 이쪽은 좁힌다 — **CR 은 어디서도 데이터가 아니지만
공백은 데이터일 수 있기 때문**이다. 같은 이유로 게이트 둘을 합치지 않았다.

마크다운의 «강제 줄바꿈» 은 어떻게 했나
--------------------------------------
줄 끝 공백 **2칸**은 GFM 에서 ``<br>`` 를 뜻한다. 그래서 지우기 전에 셌다 —
🔬 실측 2026-09-30: 82건 중 **진짜 강제 줄바꿈은 0건**이었다
(40건은 «줄 전체가 공백» 이고 42건은 1칸이거나 다음 줄이 비어 있어 렌더에 영향이 없다).
그리고 이 저장소의 **추적 ``.md`` 는 이미 0건**이므로 정책은 이미 정해져 있었다.
⚠️ 앞으로 진짜 ``<br>`` 가 필요하면 **``<br>`` 를 직접 쓴다** — 보이지 않는 공백에 의미를 싣지 않는다.

🔴 이 게이트가 **못 하는 것** (한계 선언)
-----------------------------------------
- **코드블록 안을 구별하지 않는다.** ``.md`` 의 fenced code block 안에 의도한 공백이 있어도 지운다.
- **탭이 문법인 파일**은 이름으로만 면제한다(``Makefile``). 새 종류가 생기면 손으로 더한다.
- **목록 밖 확장자는 아예 안 본다** — 위 «가려서 보는 이유» 의 대가다.

사용
----
    uv run python -m scripts.gates.code.check_whitespace          # 검사
    uv run python -m scripts.gates.code.check_whitespace --fix    # 자동 수정
"""

import os
from pathlib import Path
import subprocess
import sys

from scripts.gates._root import REPO_ROOT

if hasattr(sys.stdout, "reconfigure"):
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
  sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 🔴 이스케이프 리터럴을 쓰지 않는다 (대장 `D45`① — 전달 계층에서 한 겹 벗겨진다).
LF = bytes([10])
TAB = bytes([9])
SPACE = bytes([32])

#: 볼 확장자 — **소스와 문서만**. 데이터·자산·키는 목록에 없으므로 대상 밖이다.
TARGET_EXT = frozenset({
  ".md",
  ".py",
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".mjs",
  ".cjs",
  ".json",
  ".yml",
  ".yaml",
  ".toml",
  ".css",
  ".sh",
})

#: 🔴 대상을 **«우리가 쓰는 파일»** 로 정의한다 — 확장자·폴더 제외 목록을 늘리는 방식은 실패했다.
#:    실측 2026-09-30: 목록을 세 번 늘려도 생성물이 계속 나왔다(`.import_linter_cache` · `logs` ·
#:    `.auth` · `playwright-report.json` · `test-results`). **빼는 목록은 끝이 없다.**
#:    ⇒ 대신 **들어오는 목록**으로 뒤집었다: **추적 파일과 `docs-private/` 를 합친 것**.
#:    🔑 도구가 만드는 것은 대개 gitignore 되고 `docs-private/` 밖이므로 **자동으로 빠진다.**
PRIVATE_DIR = "docs-private"

#: 탭이 **문법인** 파일 — 들여쓰기 검사에서만 면제한다.
TAB_IS_SYNTAX = frozenset({"Makefile", "makefile"})

#: 🔑 바닥값 — 0건은 *"깨끗하다"* 가 아니라 *"못 셌다"* 다.
#:    ⚠️ 실측 2026-09-30: 대상 **716개**(생성물 제외 후). 손으로 올린다.
#:    🔬 처음 **436** 이라 적었는데 그건 세어 보지 않고 쓴 수였다 — 돌려 보니 721 이었다(`D52`).
MIN_SCANNED = 650


def targets() -> list[Path]:
  """검사 대상 — **추적 파일과 `docs-private/` 를 합친 것**.

  Returns:
      중복 없는 경로 목록 (정렬).
  """
  # 실행파일은 PATH 로 해석(부분경로 의도적) -> S607 예외 — `check_layers` 와 같은 관례
  listed = subprocess.run(
    ["git", "ls-files", "-z"],  # noqa: S607
    capture_output=True,
    check=False,
    cwd=REPO_ROOT,
  ).stdout.decode("utf-8", "surrogateescape")
  found = {REPO_ROOT / name for name in listed.split(chr(0)) if name.strip()}
  private = REPO_ROOT / PRIVATE_DIR
  if private.is_dir():
    found |= set(private.rglob("*"))
  return sorted(item for item in found if item.is_file())


def audit(fix: bool) -> tuple[int, list[tuple[str, str, int]]]:
  """공백 위생을 검사하고, ``fix`` 면 고친다.

  Args:
      fix: 참이면 파일을 고쳐 쓴다.

  Returns:
      (검사한 파일 수, [(경로, 무엇, 건수)]).
  """
  scanned = 0
  findings: list[tuple[str, str, int]] = []

  for path in targets():
    if path.suffix.lower() not in TARGET_EXT:
      continue
    rel = path.relative_to(REPO_ROOT)
    try:
      blob = path.read_bytes()
    except OSError:
      continue
    scanned += 1
    name = rel.as_posix()

    lines = blob.split(LF)
    trailing = sum(1 for line in lines if line.endswith((SPACE, TAB)))
    tabbed = 0
    if path.name not in TAB_IS_SYNTAX:
      tabbed = sum(1 for line in lines if line.startswith(TAB))
    no_final = 1 if blob and not blob.endswith(LF) else 0
    extra_final = 1 if blob.endswith(LF + LF) else 0

    if trailing:
      findings.append((name, "줄끝 공백", trailing))
    if tabbed:
      findings.append((name, "탭 들여쓰기", tabbed))
    if no_final:
      findings.append((name, "파일 끝 개행 없음", 1))
    if extra_final:
      findings.append((name, "파일 끝 빈 줄", 1))

    if fix and (trailing or no_final or extra_final):
      fixed = LF.join(line.rstrip(SPACE + TAB) for line in blob.split(LF))
      fixed = fixed.rstrip(LF) + LF if fixed.strip() else fixed
      if fixed != blob:
        stat = path.stat()
        path.write_bytes(fixed)
        # 🔴 docs-private 은 git 밖이라 mtime 이 그 문서의 유일한 «언제» 다 (FILING §12-1 · 대장 D37)
        os.utime(path, (stat.st_atime, stat.st_mtime))

  return scanned, findings


def main() -> int:
  """공백 위생을 검사한다.

  Returns:
      종료코드 — 0 이면 통과.
  """
  fix = "--fix" in sys.argv
  scanned, findings = audit(fix)

  if scanned < MIN_SCANNED:
    print("❌ 공백 위생 검사 실패 — **검사 범위가 줄었다**")
    print(f"   - 대상 {scanned}개는 바닥값 {MIN_SCANNED} 아래다")
    print("   🔑 0건은 «깨끗하다» 가 아니라 «못 셌다» 다 — TARGET_EXT 와 SKIP_DIRS 를 먼저 의심한다.")
    return 1

  if fix:
    scanned, findings = audit(False)
    print(f"🔧 자동 수정 후 재검사 — 대상 {scanned}개 · 남은 지적 {len(findings)}건")

  if findings:
    print(f"❌ 공백 위생 {len(findings)}건 (대상 {scanned}개)")
    for name, what, count in findings[:15]:
      print(f"   - {name}  {what} {count}건")
    if len(findings) > 15:
      print(f"   … 외 {len(findings) - 15}건")
    print()
    print("   ✅ 고치는 법: `--fix` 를 붙여 다시 돌린다.")
    print("   🔑 `trailing-whitespace` 훅은 **staged 파일만** 본다 — gitignore 된 문서는 이 게이트가 맡는다.")
    return 1

  print(f"✅ 공백 위생 — 대상 {scanned}개 · 줄끝 공백 0 · 탭 들여쓰기 0 · 끝 개행 정상.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
