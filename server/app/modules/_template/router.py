"""새 기능 모듈을 만들 때 복사해서 쓰는 틀.

1. 이 _template 폴더를 복사해서 이름을 바꾼다. 예) review
2. 아래 router 에 API 를 추가한다.
3. 서버를 다시 켜면 /api/review/... 로 자동 연결된다.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
def ping():
    return {"module": __package__.rsplit(".", 1)[-1], "status": "ok"}
