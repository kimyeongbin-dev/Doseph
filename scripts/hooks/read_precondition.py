"""`PreToolUse` 훅 — **읽기를 «결정» 에서 «전제조건» 으로 바꾼다** (트랙 B-10).

왜 훅이어야 하나
----------------
이 저장소의 장치는 거의 전부 **사후**다 — `pre-commit`·`pre-push` 는 일을 끝낸 뒤 막는다.
사전 장치는 `CLAUDE.md`(층②, 매 턴 토큰)와 저장소 문서(층⑤, **`Read` 를 불러야만**)뿐이다.

> *"필요할 때 읽어라"* 는 **이미 아는 사람에게만 작동한다.** 읽어야 할 상황임을 알려면
> 그걸 읽어야 알기 때문이다 — **순환**이다(대장 **D38** 이 그 실증: 규칙을 쓴 다음 턴에 어겼다).

**`PreToolUse` 만이 «사전 + 판단 불필요» 칸을 채운다.**

무엇을 하나
-----------
1. `Read` 로 **라우팅 문서**를 열면 → 세션 마커를 남긴다(조용히 통과).
2. `Write`/`Edit` 로 **`docs-private/**.md`** 를 고치려 하면
   → 마커가 없으면 **deny + 어디를 읽어라**, 있으면 통과하며 **상시 세트를 주입**한다.

훅은 **1종**이다(`matcher` 하나). 안에서 `tool_name` 으로 분기한다 — 계승 계획의
정지 규칙(*훅을 여러 개 만들지 않는다. 1종으로 시작해 오탐을 재고 늘린다*)을 지킨다.

🔴 이 훅이 **못 하는 것** (한계 선언)
--------------------------------------
- **읽은 «내용» 을 모른다.** `Read` 를 불렀다는 사실만 안다 — 훑었는지 정독했는지는 모른다.
- **통째로 꺼질 수 있다**(`disableAllHooks`·관리 정책). 그래서 **최소 핵 8줄은 `CLAUDE.md`
  본문에 상주**시켜 훅과 무관하게 살게 했다. 훅에 «전부» 를 걸지 않는다.
- **성공은 보이지 않는다** — UI 는 훅이 실패하거나 느릴 때만 표시한다. *"돌았나"* 는 따로 재야 한다.
- **자기 배선을 스스로 못 본다** → `scripts/gates/tooling/check_claude_hooks.py` 가 pre-push 에서 센다.
- 🔴 **읽음 마커는 압축을 살아남지만 «읽은 내용» 은 안 살아남는다**(2026-09-22 실측, **QA-50**).
  `Read` 를 불렀다는 사실만 기록하므로, 압축 후에는 **보증이 빈 채로 통과**한다.
  즉 이 훅이 막는 것은 *"한 번도 안 읽고 고치는 것"* 이지 *"지금 들고 있는가"* 가 아니다.

🟡 **내부 오류가 나면 «통과» 시킨다(fail-open).** 의도된 선택이다 —
버그로 전부 막히면 **사람이 훅을 통째로 끄고, 그러면 검출률이 0 이 된다**(`QUALITY_GATES` §2-8).
대신 오류를 `systemMessage` 로 **드러낸다.** 조용히 실패하지는 않는다.
"""

import json
import os
from pathlib import Path
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKER_ROOT = Path(tempfile.gettempdir()) / "doseph-read-precondition"

# 읽어야 통과하는 문서 — 키는 마커 이름, 값은 파일명 조각.
GATED_DOC = "FILING.md"
# 「상시 세트를 이미 주입했다」 기록. `PostCompact` 가 이것만 지운다.
INJECTED = "상시세트-주입됨"
# 규약 밖 구역은 묻지 않는다(미분류·죽은 문서를 옮기는 일이 막히면 오탐이 된다).
EXEMPT_PARTS = ("/_unfiled/", "/_legacy/")


# ── 세션 마커 ────────────────────────────────────────────────────────
# 흐름: session_id 로 디렉터리 -> 읽은 문서 이름으로 빈 파일
# 세션이 끝나면 임시 디렉터리와 함께 자연히 사라진다(상태를 저장소에 남기지 않는다).
def marker_path(session_id: str, name: str) -> Path:
    """세션·문서별 마커 경로를 만든다.

    Args:
        session_id: 훅 입력의 `session_id`.
        name: 문서 이름.

    Returns:
        마커 파일 경로.
    """
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64] or "nosession"
    return MARKER_ROOT / safe / name


def decide(payload: dict[str, object]) -> dict[str, object] | None:
    """훅 입력을 보고 통과·차단·주입을 정한다.

    Args:
        payload: stdin 으로 온 훅 입력.

    Returns:
        훅 출력 dict. `None` 이면 아무 말 없이 통과.
    """
    tool = str(payload.get("tool_name", ""))
    session = str(payload.get("session_id", ""))
    raw_input = payload.get("tool_input")
    tool_input: dict[str, object] = raw_input if isinstance(raw_input, dict) else {}
    path = str(tool_input.get("file_path", "")).replace("\\", "/")

    # ① Read — 라우팅 문서를 열었으면 기록만 하고 빠진다.
    if tool == "Read":
        if path.endswith(GATED_DOC):
            m = marker_path(session, GATED_DOC)
            m.parent.mkdir(parents=True, exist_ok=True)
            m.touch()
        return None

    # ② Write/Edit — docs-private 의 문서를 고칠 때만 묻는다.
    if tool not in ("Write", "Edit"):
        return None
    if "/docs-private/" not in path or not path.endswith(".md"):
        return None
    if any(part in path for part in EXEMPT_PARTS):
        return None

    if marker_path(session, GATED_DOC).exists():
        # 🔴 상시 세트는 **세션당 한 번만** 주입한다.
        #    한 번 들어오면 이미 컨텍스트에 있으므로 같은 340자를 매 편집마다 다시 넣는 것은
        #    순수한 낭비다(실측: 25회 편집 = 약 7,000 토큰 → 1회 = 약 283 토큰).
        #    ⚠️ **대가**: 압축 이후에는 주입분이 컨텍스트에서 사라지는데 마커는 남는다.
        #    → **`PostCompact` 훅이 `--reset-injection` 으로 이 마커를 지운다**(2026-09-22, B-10 2구간).
        #    그래도 훅이 통째로 꺼진 경우엔 **최소 핵 8줄(`CLAUDE.md` §6-5)**이 그 공백을 받는다.
        injected = marker_path(session, INJECTED)
        if injected.exists():
            return None
        injected.parent.mkdir(parents=True, exist_ok=True)
        injected.touch()
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    "★ 상시 세트(대장 상단) — 무엇을 하든 걸린다: "
                    "D31 즉석 grep 으로 정본 검증기를 뒤집지 않는다 · "
                    "D43 «몇 건인가» 는 질문이 덜 된 질문이다(세는 대상을 먼저) · "
                    "D47 구조를 문자열로 세지 않는다(단위를 붙인다) · "
                    "D52 세기 전에 기대 범위를 먼저 말한다 · "
                    "D58 빈칸에 이름 붙이기 전에 그 자리를 열어 본다 · "
                    "D13 소스를 안 읽고 도구 동작을 단정하지 않는다 · "
                    "D14 인과 사슬의 한 고리만 보고 «원인» 이라 하지 않는다 · "
                    "D17 «다 기록했나» 는 두 패스다(내 변경이 기존을 거짓으로 만들었나). "
                    "지금은 문서를 고치는 중이니 축 `문서-닫기`(18건)도 함께 본다."
                ),
            }
        }

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"`docs-private/` 문서를 고치기 전에 **docs-private/{GATED_DOC}** 를 먼저 읽어라 "
                "(§3-1: 파일명은 «모양» 만 보증한다 — 정독 없이 분류하지 않는다, 대장 D38). "
                "그리고 실수 대장의 축 `문서-닫기` 를 함께 본다."
            ),
        }
    }


# ── `PostCompact` — 압축이 컨텍스트를 갈아엎었으니 주입 기록을 무른다 ──
# 흐름: 세션 마커 폴더 -> «주입됨» 만 삭제 -> 다음 PreToolUse 가 다시 주입
# 🔑 **«읽음» 마커는 지우지 않는다** — 지금은. 설계 근거는 *"읽었다는 사실은 압축으로 변하지 않는다"*
#    였는데, 2026-09-22 실발동 측정에서 **반쪽만 참**임이 드러났다: `Read` 를 불렀다는 사실은 남지만
#    **읽은 내용은 요약에서 탈락한다.** 그래서 압축 후 첫 편집은 **보증이 빈 채로 통과**한다.
#    🔴 읽음 마커도 지우는 것이 **오탐이 아니라 정탐**일 수 있다 — 판정 대기 = **QA-50**.
#    지금 지우는 것은 *"컨텍스트에 있다"* 를 뜻하는 **주입 마커뿐**이다.
# 🔴 왜 직접 주입하지 않나: `PostCompact` 가 `additionalContext` 를 지원하는지
#    **실측하지 않았다.** 이 방식은 훅이 **돌기만** 하면 되므로 그 미지수에 기대지 않는다.
def reset_injection(session_id: str) -> int:
    """압축 후 «상시 세트 주입됨» 기록만 지운다.

    Args:
        session_id: 훅 입력의 `session_id`. 비어 있으면 모든 세션을 훑는다.

    Returns:
        종료코드 — 항상 0.
    """
    targets = [marker_path(session_id, INJECTED)] if session_id else list(MARKER_ROOT.glob(f"*/{INJECTED}"))
    for t in targets:
        t.unlink(missing_ok=True)  # 없어도 죽지 않는다 — 압축이 두 번 와도 안전
    return 0


def main() -> int:
    """Stdin 을 읽어 판정하고 stdout 으로 답한다.

    Returns:
        종료코드 — 항상 0. 차단은 종료코드가 아니라 `permissionDecision` 으로 한다.
    """
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if "--reset-injection" in sys.argv:
            return reset_injection(str(payload.get("session_id", "")) if isinstance(payload, dict) else "")
        out = decide(payload if isinstance(payload, dict) else {})
    except Exception as exc:
        json.dump({"systemMessage": f"⚠️ read-precondition 훅 내부 오류(통과시킴): {exc}"}, sys.stdout)
        return 0
    if out is not None:
        json.dump(out, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
