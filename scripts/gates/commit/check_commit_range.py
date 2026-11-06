"""이미 만들어진 커밋들의 메시지를 범위로 검사한다 (pre-push · CI).

**왜 commit-msg 훅만으로 부족한가**: 그 훅은 이 컴퓨터에서 쓴 커밋만 본다. Dependabot 이 만든
커밋(78자 제목 + 본문 7,726자)은 훅을 거치지 않았고, `git merge` 가 남긴 `# Conflicts:` 줄은
훅 시점에 편집기 주석과 구별할 수 없다(편집기를 쓰면 git 이 나중에 지운다).
그래서 **최종 커밋 객체**를 푸시 전과 CI 에서 다시 본다.

✅ 음성 대조: `Merge pull request ...`·`Revert "..."` 는 git 이 만든 제목이라 길어도 통과한다.
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from scripts.gates.commit.check_commit_subject import SUBJECT_MAX

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 본문 상한(코드 포인트). 사람이 쓴 최장 본문이 1,579자라 그 위로 잡았다.
BODY_MAX = 2000

#: 이 커밋까지는 검사하지 않는다. 2026-11-05 이력을 고칠 때 dev 끝이었고,
#: 그 이전에는 51자 제목 3건이 남아 있다(고치려면 이력을 더 넓게 다시 써야 한다).
HISTORY_FLOOR = "e674f5bee8b88a558a6ffd6641ab95f37d08fcda"

#: `git log` 레코드 구분자. 커밋 메시지에 나올 수 없는 제어 문자를 쓴다.
SEPARATOR = "\x1e"


# ── 메시지 한 건 판정 ─────────────────────────────────────────────────
# 흐름: 제목 길이(git 생성 제목 제외) -> 충돌 주석 잔재 -> 본문 길이
def message_problems(message: str) -> list[str]:
  """최종 커밋 메시지의 규약 위반을 돌려준다.

  Args:
      message: 커밋 메시지 전문.

  Returns:
      위반 설명 목록. 없으면 빈 리스트.
  """
  subject, _, body = message.strip().partition("\n")
  problems = []
  if len(subject) > SUBJECT_MAX and not subject.startswith(("Merge ", "Revert ")):
    problems.append(f"제목 {len(subject)}자 (상한 {SUBJECT_MAX})")
  if any(line.startswith("# Conflicts:") for line in message.splitlines()):
    problems.append("`# Conflicts:` 주석이 메시지에 남았다")
  if len(body.strip()) > BODY_MAX:
    problems.append(f"본문 {len(body.strip())}자 (상한 {BODY_MAX})")
  return problems


# ── 범위 읽기 ─────────────────────────────────────────────────────────
# 흐름: 범위에서 바닥 커밋의 조상을 빼고 -> (해시, 메시지) 목록으로 나눈다
# 얕은 클론에는 바닥 커밋이 없으므로 CI 는 fetch-depth: 0 이어야 한다. 없으면 git 이 실패해 멈춘다.
def read_commits(revision_range: str) -> list[tuple[str, str]]:
  """범위 안 커밋의 (짧은 해시, 메시지) 를 돌려준다."""
  output = subprocess.run(
    ["git", "log", f"--format=%h%n%B{SEPARATOR}", revision_range, "--not", HISTORY_FLOOR],  # noqa: S607
    capture_output=True,
    check=True,
    encoding="utf-8",
  ).stdout
  commits = []
  for record in output.split(SEPARATOR):
    short, _, message = record.strip().partition("\n")
    if short:
      commits.append((short, message))
  return commits


def default_range() -> str:
  """pre-push 면 pre-commit 이 넘긴 범위를, 아니면 dev 이후를 쓴다."""
  source = os.environ.get("PRE_COMMIT_FROM_REF")
  target = os.environ.get("PRE_COMMIT_TO_REF")
  if source and target:
    return f"{source}..{target}"
  return "origin/dev..HEAD"


# ── 범위 검사 (pre-push · CI) ─────────────────────────────────────────
# 흐름: 범위 결정 -> 커밋별 판정 -> 위반이 있으면 고치는 방법과 함께 실패
def main() -> int:
  """지정한 범위의 커밋 메시지를 검사한다."""
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--range", dest="revision_range", default=None)
  parser.add_argument("--message-file", type=Path, default=None, help="파일 한 건만 판정한다(게이트 검증용)")
  args = parser.parse_args()

  if args.message_file:
    commits = [("(file)", args.message_file.read_text(encoding="utf-8"))]
  else:
    commits = read_commits(args.revision_range or default_range())

  failed = [(short, message_problems(message), message) for short, message in commits]
  failed = [item for item in failed if item[1]]
  print(f"[commit-range] 커밋 {len(commits)}건 검사 · 위반 {len(failed)}건")
  if not failed:
    return 0
  for short, problems, message in failed:
    print(f"  {short} {message.splitlines()[0][:70]}: {' · '.join(problems)}", file=sys.stderr)
  print(
    "\n  내 커밋이면 메시지를 고쳐 다시 푸시한다."
    "\n  Dependabot PR 이면 제목을 지정해 squash 로 머지한다 (CONTRIBUTING.md §3):"
    '\n    gh pr merge <번호> --squash --subject "chore(deps): ..." --body ""\n',
    file=sys.stderr,
  )
  return 1


if __name__ == "__main__":
  sys.exit(main())
