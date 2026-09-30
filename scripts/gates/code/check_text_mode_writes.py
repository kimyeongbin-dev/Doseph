r"""텍스트 모드 쓰기 게이트 — **CRLF 를 만드는 «원인» 을 코드에서 막는다**.

왜 결과 게이트만으로는 부족한가
-------------------------------
옆에 `check_line_endings` 가 있다. 그것은 **파일에 CR 이 있으면** 실패한다 — 정확하지만 **사후**다.
🔬 실측 2026-09-30 이 그 한계를 보였다: 워킹트리 CR 을 **0** 으로 만든 직후
``build_followup_index`` 를 한 번 돌렸더니 ``FOLLOWUP_INDEX.md`` 에 **CRLF 212개**가 즉시 돌아왔다.

⇒ 결과만 막으면 **«돌린다 → 오염된다 → 게이트 Red → 고친다 → 또 돌린다»** 가 반복된다.
그 반복이 곧 시간 낭비이고, 이 게이트는 그 고리를 **코드 쪽에서** 끊는다.

무엇이 범인인가
---------------
Windows 의 파이썬 **텍스트 모드**다. ``Path.write_text()`` 와 ``open(f, "w")`` 는
``newline=None`` 이 기본값이라 줄바꿈을 ``os.linesep``(= CRLF)으로 **조용히 번역**한다.

🔑 **전역으로 끌 방법이 없다**(실측 2026-09-30):

- ``open()`` 의 ``newline`` 기본값을 바꾸는 **환경변수·설정이 CPython 에 없다**.
- ``os.linesep`` 은 코드로 바꿀 수 없다.
- 저장소 루트의 ``sitecustomize.py`` 는 ``uv run`` 에서 **로드되지 않는다**
  (``-c`` · ``-m`` · 스크립트 세 방식 모두 확인).

⇒ 남은 길은 **호출마다 명시**하는 것뿐이고, 그래서 기계가 센다.

```python
path.write_text(text, encoding="utf-8", newline="\n")  # ✅
path.write_bytes(text.encode("utf-8"))  # ✅ 더 확실하다
path.write_text(text, encoding="utf-8")  # ❌ Windows 에서 CRLF 가 된다
```

🔴 이 게이트가 **못 하는 것** (한계 선언)
-----------------------------------------
- **테스트는 보지 않는다.** ``tests`` 아래는 대개 ``tmp_path``(저장소 **밖**)에 쓰므로
  워킹트리를 오염시키지 않는다 — **재발원이 아니다**. 실측 2026-09-30: 테스트 21건 전부 그 형태였다.
  ⚠️ 그래서 *«테스트가 저장소 파일을 텍스트 모드로 쓰는»* 경우는 **이 게이트를 통과한다.**
  그건 `check_line_endings` 가 결과로 잡는다 — **둘이 짝이다.**
- **다른 쓰기 경로를 모른다.** ``csv.writer`` · ``json.dump(fp)`` · ``open`` 을 감싼 헬퍼 ·
  ``subprocess`` 리다이렉트는 보지 않는다. 이름으로 찾는 검사의 한계다.
- **``newline`` 의 «값» 을 검증하지 않는다.** ``newline=os.linesep`` 이라고 써도 통과한다.
  값까지 보려면 상수 추적이 필요하고, 그건 오탐을 부른다.

사용
----
    uv run python -m scripts.gates.code.check_text_mode_writes
"""

import ast
import sys

from scripts.gates._root import REPO_ROOT

if hasattr(sys.stdout, "reconfigure"):
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
  sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 들어가지 않는 곳 — 생성물·의존성·캐시.
SKIP_DIRS = frozenset({
  ".git",
  "node_modules",
  "__pycache__",
  ".venv",
  ".next",
  ".ruff_cache",
  ".pytest_cache",
  ".mypy_cache",
  "htmlcov",
  ".uv-cache",
  "dist",
  "build",
})

#: 🔴 테스트는 «재발원이 아니라» 제외한다 — 위 한계 선언을 함께 읽는다.
TEST_PARTS = frozenset({"tests"})

#: 🔑 바닥값 — 0건은 *"위반이 없다"* 가 아니라 *"못 셌다"* 다.
#:    AST 가 안 돌거나 경로 필터가 틀리면 **대상 0건을 초록으로 보고**한다.
#:    ⚠️ 실측 2026-09-30: 본코드 ``write_text`` **10건**(전부 ``newline`` 명시). 손으로 올린다.
MIN_CHECKED = 8


def is_text_write_open(node: ast.Call) -> bool:
  """``open(..., "w")`` 처럼 **텍스트 쓰기 모드**로 여는 호출인가.

  Args:
      node: 검사할 호출 노드.

  Returns:
      텍스트 쓰기 모드면 ``True`` (바이너리 ``b`` 가 붙으면 ``False``).
  """
  name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
  if name != "open":
    return False
  mode = ""
  if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
    mode = str(node.args[1].value)
  for keyword in node.keywords:
    if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
      mode = str(keyword.value.value)
  return ("w" in mode or "a" in mode) and "b" not in mode


def audit() -> tuple[int, list[tuple[str, int, str]]]:
  """저장소의 텍스트 모드 쓰기 호출을 센다.

  Returns:
      (검사한 호출 수, [(경로, 줄, 무엇)]).
  """
  checked = 0
  offenders: list[tuple[str, int, str]] = []

  for path in REPO_ROOT.rglob("*.py"):
    parts = path.relative_to(REPO_ROOT).parts
    if any(part in SKIP_DIRS for part in parts) or any(part in TEST_PARTS for part in parts):
      continue
    try:
      tree = ast.parse(path.read_bytes().decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
      continue
    for node in ast.walk(tree):
      if not isinstance(node, ast.Call):
        continue
      kwargs = {keyword.arg for keyword in node.keywords}
      what = ""
      if getattr(node.func, "attr", None) == "write_text":
        what = "write_text"
      elif is_text_write_open(node):
        what = "open(쓰기 모드)"
      if not what:
        continue
      checked += 1
      if "newline" not in kwargs:
        offenders.append((path.relative_to(REPO_ROOT).as_posix(), node.lineno, what))

  return checked, offenders


def main() -> int:
  """텍스트 모드 쓰기에 ``newline`` 이 명시됐는지 검사한다.

  Returns:
      종료코드 — 0 이면 통과.
  """
  checked, offenders = audit()

  if checked < MIN_CHECKED:
    print("❌ 텍스트 모드 쓰기 검사 실패 — **검사 범위가 줄었다**")
    print(f"   - 검사한 호출 {checked}건은 바닥값 {MIN_CHECKED} 아래다")
    print("   🔑 0건은 «위반이 없다» 가 아니라 «못 셌다» 다 — 경로 필터나 AST 파싱을 먼저 의심한다.")
    return 1

  if offenders:
    print(f"❌ 텍스트 모드 쓰기 {len(offenders)}건 — `newline` 이 없다 (검사 {checked}건 중)")
    for name, lineno, what in offenders:
      print(f"   - {name}:{lineno}  {what}")
    print()
    print("   🔑 Windows 에서 텍스트 모드는 줄바꿈을 CRLF 로 **조용히 번역**한다.")
    print("      `git diff` 도 `wc -l` 도 정상이라고 답하므로 **눈으로는 안 보인다**(대장 `D74`).")
    print("   ✅ `write_bytes()` 를 쓰거나, `newline` 을 줄바꿈 문자로 **명시**한다.")
    return 1

  print(f"✅ 텍스트 모드 쓰기 — 호출 {checked}건 전부 `newline` 명시.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
