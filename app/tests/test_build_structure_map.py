"""구조 지도 생성기 단위 테스트 (트랙 B-14, `문서-9`).

⚠️ `tmp_path` 표본만 쓴다 — 저장소 상태에 따라 결과가 바뀌면 그건 생성기 테스트가 아니라
저장소 스냅샷이다(`check_folder_index` 테스트와 같은 규약).

🔴 **이 생성기가 존재하는 이유**: 손으로 쓴 `PROJECT_STRUCTURE_REPORT.md` 가 5개월 만에
**12개 항목이 전부 틀려** 은퇴했다(저장소명·PG 버전·JWT 알고리즘·라우터 9 vs 실제 15 ·
"10개 테이블" vs 실제 18 · 없는 모델 2개…). 대안은 *다시 쓰기* 가 아니라 **생성**이다.

🔑 **구조를 문자열로 세지 않는다**(대장 `D47`) — 라우터 엔드포인트도 모델도 **AST** 로 센다.
정규식으로 `@router.get` 을 찾으면 주석·문자열·docstring 안의 것을 줍는다.
"""

from pathlib import Path

from scripts.build_structure_map import (
    Axis,
    collect_frontend_routes,
    collect_models,
    collect_routers,
    render,
)

ROUTER_SRC = '''
"""라우터 예시.

    @router.get("/docstring-안") — 이건 엔드포인트가 아니다.
"""
from fastapi import APIRouter

router = APIRouter()

EXAMPLE = "@router.post('/문자열-안')"   # 이것도 아니다


@router.get("/items")
async def list_items() -> None: ...


@router.post("/items")
async def create_item() -> None: ...


@router.delete("/items/{item_id}")
async def delete_item() -> None: ...


def helper() -> None:
    """데코레이터가 없다 — 엔드포인트가 아니다."""
'''

MODEL_SRC = """
from tortoise import fields
from tortoise.models import Model


class Medicine(Model):
    name = fields.CharField(max_length=100)

    class Meta:
        table = "medicine_info"


class _Mixin:
    '''Model 을 상속하지 않는다 — 테이블이 아니다.'''
"""


def make_pkg(tmp_path: Path, rel: str, files: dict[str, str]) -> Path:
    """표본 패키지를 만든다.

    Args:
        tmp_path: pytest 임시 디렉터리.
        rel: 저장소 루트 기준 상대 경로.
        files: 파일명 → 본문.

    Returns:
        만들어진 저장소 루트.
    """
    folder = tmp_path / rel
    folder.mkdir(parents=True)
    for name, body in files.items():
        (folder / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_router_endpoints_are_counted_by_ast(tmp_path: Path) -> None:
    """🔑 docstring·문자열 안의 `@router.get` 을 **줍지 않는다** — 그게 `D47` 이 말하는 것이다."""
    root = make_pkg(tmp_path, "app/apis/v1", {"item_routers.py": ROUTER_SRC})

    axis = collect_routers(root)

    assert axis.count == 1, "라우터 «파일» 은 1개다"
    assert axis.detail["엔드포인트"] == 3, "docstring 1 + 문자열 1 을 빼고 3개여야 한다"


def test_router_without_decorator_is_not_an_endpoint(tmp_path: Path) -> None:
    """음성 대조 — 데코레이터 없는 함수는 세지 않는다."""
    root = make_pkg(tmp_path, "app/apis/v1", {"empty_routers.py": "def plain() -> None: ...\n"})

    axis = collect_routers(root)

    assert axis.count == 1
    assert axis.detail["엔드포인트"] == 0


def test_models_need_a_model_base(tmp_path: Path) -> None:
    """🔑 `Model` 을 상속한 클래스만 테이블이다 — 파일 수로 세면 mixin 이 섞인다."""
    root = make_pkg(tmp_path, "app/models", {"medicine.py": MODEL_SRC, "__init__.py": ""})

    axis = collect_models(root)

    assert axis.detail["모델 클래스"] == 1
    assert "Medicine" in axis.items[0]


def test_frontend_routes_come_from_page_files(tmp_path: Path) -> None:
    """`page.jsx` 의 **경로**가 곧 라우트다 — 파일 이름이 아니라."""
    root = tmp_path
    for rel in ("src/app", "src/app/medication", "src/app/medication/detail"):
        (root / "medication-frontend" / rel).mkdir(parents=True, exist_ok=True)
        (root / "medication-frontend" / rel / "page.jsx").write_text("x", encoding="utf-8")

    axis = collect_frontend_routes(root)

    assert axis.count == 3
    assert "/" in axis.items
    assert "/medication/detail" in axis.items


def test_missing_folder_is_fail_closed(tmp_path: Path) -> None:
    """🔴 폴더가 없으면 **«0개» 가 아니라 «못 셌다»** 다 — 경로가 바뀌면 조용히 0이 된다."""
    axis = collect_routers(tmp_path)

    assert axis.problem is not None
    assert axis.count == 0


def test_floor_catches_a_shrinking_axis(tmp_path: Path) -> None:
    """🔴 **줄어든 것도 실패로 본다** — `check_utf8_guard` 가 11건 → 1건이 되고도 초록이었다(`D31`)."""
    root = make_pkg(tmp_path, "app/apis/v1", {"a_routers.py": "router = 1\n"})

    axis = collect_routers(root, floor=5)

    assert axis.problem is not None
    assert "바닥값" in axis.problem


def test_render_stamps_when_and_from_what(tmp_path: Path) -> None:
    """🔑 생성물은 **언제·무엇에서** 만들어졌는지 스스로 말해야 한다.

    은퇴한 구조 보고서가 위험했던 이유는 틀린 것 자체가 아니라 **틀린 줄 몰랐다**는 것이다.
    """
    axes = [Axis(name="라우터", items=["a"], detail={"엔드포인트": 3}, floor=1)]

    out = render(axes, root=tmp_path)

    assert "생성" in out
    assert "커밋하지 않는다" in out
    assert "라우터" in out
    # 🔑 생성물도 `doc-meta` 를 단다 — 직하 규약의 예외가 아니다(`FOLLOWUP_INDEX` 선례).
    assert "<!-- doc-meta" in out
    assert "status:   current" in out


def test_render_declares_what_it_does_not_know(tmp_path: Path) -> None:
    """🔴 **모르는 것을 «모른다» 고 적는 칸**이 이 지도의 핵심이다.

    앞 판이 *"10개 테이블"* 이라 틀린 이유는 세다 틀린 게 아니라 **코드에서 추측**했기
    때문이다. 실제 테이블은 DB 가 정본이다.
    """
    out = render([Axis(name="라우터", items=["a"], floor=1)], root=tmp_path)

    assert "모르는 것" in out
    assert "DB 테이블" in out
