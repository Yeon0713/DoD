"""팀 시험용으로 서버 켜기. 가상환경을 켠 뒤:

    python run_dev.py            (server/ 폴더에서. 다른 폴더에서는 python server/run_dev.py)

`uvicorn app.main:app` 과 같은 서버를, 데모 테스트 모드를 시험할 때 쓰는 설정으로 켠다. Windows, Mac 에서 명령이 같다.
  - 시험용 기능을 연다 (DEV_CLOCK_ENABLED=true): 앱 시작 화면 메뉴의 초기화(/dev/reset), 시계 앞당기기(/dev/clock)
  - 주소는 http://127.0.0.1:8000 (앱의 mobile/.env.local 과 같다)
  - 켜기 전에 8000번 포트를 이미 쓰는 프로그램이 있는지 본다. 예전에 켠 서버가 남아 있으면 브라우저가 그쪽으로 붙어서
    새 코드가 안 보이거나 응답이 오지 않는다 (Windows 는 같은 포트에 서버가 두 개 켜져도 오류가 나지 않는다)
  - server/.env 에 어떤 키가 채워져 있는지 알려 준다 (값은 보여 주지 않는다)

코드를 고치며 개발할 때는 예전처럼 `uvicorn app.main:app --reload` 를 써도 된다.
"""

import os
import socket
import sys
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8000"))


def port_in_use(port: int) -> bool:
    """그 포트를 이미 쓰는 프로그램이 있는지. 직접 한 번 잡아 보고 바로 놓는다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == "nt":
            # Windows 는 SO_REUSEADDR 가 있으면 남이 쓰는 포트도 잡힌다. 혼자만 쓰겠다고 해야 겹치는 것을 알 수 있다
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # 방금 끈 서버의 흔적(TIME_WAIT) 때문에 잘못 막히지 않게 한다. 듣고 있는 서버가 있으면 그래도 실패한다
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((HOST, port))
        except OSError:
            return True
    return False


def how_to_free(port: int) -> str:
    if os.name == "nt":
        return (
            f"  netstat -ano | findstr :{port}      ← 맨 오른쪽 숫자가 프로그램 번호(PID)\n"
            f"  taskkill //F //PID <번호>           ← Git Bash 기준. 명령 프롬프트에서는 /F /PID"
        )
    return f"  lsof -ti :{port} | xargs kill"


def print_key_check() -> None:
    from app.core.config import settings

    checks = [
        ("가게 찾기 (네이버 검색)", settings.naver_api_hub_client_id and settings.naver_api_hub_client_secret, "NAVER_API_HUB_CLIENT_ID / SECRET"),
        ("가게 찾기 지도 그림", settings.naver_maps_client_id and settings.naver_maps_client_secret, "NAVER_MAPS_CLIENT_ID / SECRET"),
        ("답글 초안, 문장 다듬기 (CLOVA X)", settings.clova_studio_api_key, "CLOVA_STUDIO_API_KEY"),
    ]
    print("server/.env 확인")
    for label, filled, names in checks:
        print(f"  [{'있음' if filled else '없음'}] {label}: {names}")
    if not all(filled for _, filled, _ in checks):
        print("  '없음'인 기능은 화면에서 실패 안내가 나옵니다. 로그인과 테스트 계정은 키 없이도 됩니다.")
    login = "진짜 네이버 로그인" if settings.naver_login_client_id and settings.naver_login_client_secret else "임시 네이버 로그인 (테스트 계정 dona_test1 ~ 3)"
    print(f"  네이버 로그인: {login}")


def main() -> None:
    server_dir = Path(__file__).resolve().parent
    os.chdir(server_dir)  # .env 와 db/ 를 server/ 기준으로 읽는다
    sys.path.insert(0, str(server_dir))

    if port_in_use(PORT):
        print(f"{PORT}번 포트를 이미 쓰는 프로그램이 있어요. 예전에 켠 서버가 남아 있을 수 있어요.")
        print("그 프로그램을 끈 뒤 다시 켜 주세요:")
        print(how_to_free(PORT))
        sys.exit(1)

    os.environ.setdefault("DEV_CLOCK_ENABLED", "true")
    import uvicorn

    print_key_check()
    print(f"\n서버 주소: http://localhost:{PORT}/health  (끄기: Ctrl + C)")
    print("앱: 새 터미널에서 cd mobile 뒤 npm run web → http://localhost:8082\n")
    uvicorn.run("app.main:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
