"""게이트가 저장소 루트를 **자기 위치와 무관하게** 찾는다.

게이트를 폴더로 분류하면서 ``Path(__file__).parents[1]`` 같은 **깊이 고정** 계산이
전부 깨졌다. 폴더를 한 단계 더 나누는 순간 또 깨진다 —
**깊이를 세지 말고 표식을 찾는다.**

``pyproject.toml`` 이 있는 첫 조상이 저장소 루트다.
"""

from pathlib import Path


def repo_root() -> Path:
    """``pyproject.toml`` 을 가진 첫 조상 디렉터리.

    Returns:
        저장소 루트 경로.

    Raises:
        RuntimeError: 루트 표식을 끝까지 못 찾았을 때 (fail-closed —
            추측한 경로로 검사를 계속하면 **대상 0건을 초록으로 보고**한다).
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    message = "저장소 루트를 찾지 못했다 (pyproject.toml 없음) — 검사를 계속하면 대상 0건을 초록으로 본다"
    raise RuntimeError(message)


REPO_ROOT = repo_root()
PRIVATE = REPO_ROOT / "docs-private"
