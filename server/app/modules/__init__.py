"""기능 모듈 자동 등록.

app/modules/ 아래에 폴더를 만들고 그 안 router.py 에 `router = APIRouter()` 를 두면
서버가 켜질 때 자동으로 /api/<폴더이름> 주소에 연결된다. main.py 는 고칠 필요 없다.

이름이 _ 로 시작하는 폴더(_template 등)는 등록하지 않는다.
"""

import importlib
import pkgutil

from fastapi import APIRouter


def load_modules() -> list[tuple[str, APIRouter]]:
    modules = []
    for info in pkgutil.iter_modules(__path__):
        if not info.ispkg or info.name.startswith("_"):
            continue
        router_module = importlib.import_module(f"{__name__}.{info.name}.router")
        modules.append((info.name, router_module.router))
    return modules
