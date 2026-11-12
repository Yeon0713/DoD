import re

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """server/.env 에서 읽어오는 설정 값. 없으면 아래 기본값을 쓴다."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DoD API"
    # 서버를 부를 수 있는 웹 주소. 8082 는 mobile/ 앱을 웹으로 켠 주소, 3000 은 예전 frontend/
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8082", "http://127.0.0.1:8082"]
    # 내 컴퓨터에서 켠 앱(localhost, 127.0.0.1)은 포트가 무엇이든 받는다. 예전에 만든 .env 의 CORS_ORIGINS 에 8082 가 없거나,
    # 앱을 8081 같은 다른 포트로 켜도 서버를 부를 수 있게 한다. 배포 서버에서 끄려면 .env 에 CORS_ORIGIN_REGEX= (빈 값)
    cors_origin_regex: str = r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"

    # 로그인이 생기기 전까지 보여 줄 가게. 주소에 ?store_id=s002 를 붙이면 그 가게를 보여 준다
    demo_store_id: str = "s001"
    # 분석과 계획을 다시 계산하는 간격(분). 그 사이에는 계산해 둔 결과를 그대로 쓴다
    snapshot_refresh_minutes: int = 10
    # 로컬 시험용: /dev/clock 으로 서버 시계를 앞당길 수 있게 한다. 배포에서는 켜지 않는다
    dev_clock_enabled: bool = False
    # 매장을 등록하면 우리 전용 목업 주문·매출·알바 데이터를 그 가게 파일에 넣는다 (POS·배달앱 연동 전 시연용)
    demo_store_data: bool = True

    # 네이버 아이디로 로그인 (developers.naver.com 에 등록한 애플리케이션). 데모 시험 모드에서 쓴다
    naver_login_client_id: str = ""
    naver_login_client_secret: str = ""
    # 네이버 개발자 센터에 적은 Callback URL 과 글자 하나까지 같아야 한다
    naver_login_callback_url: str = "http://localhost:8000/api/auth/naver/callback"
    # 카드 문장을 CLOVA X 로 사장님 말투로 다듬을지. 키가 없으면 켜 있어도 원래 문장을 쓴다
    sentence_polish_enabled: bool = True

    # 네이버 클라우드 API (콘솔 > 마이페이지 > 인증키 관리). SENS 도 이 키를 쓴다.
    ncloud_access_key: str = ""
    ncloud_secret_key: str = ""

    # HyperCLOVA X (CLOVA Studio > API 키)
    clova_studio_api_key: str = ""
    clova_studio_base_url: str = "https://clovastudio.stream.ntruss.com"
    clova_studio_model: str = "HCX-005"
    clova_studio_timeout: float = 30

    # Maps (Application Services > Maps > Application 등록)
    naver_maps_client_id: str = ""
    naver_maps_client_secret: str = ""
    naver_maps_base_url: str = "https://maps.apigw.ntruss.com"

    # NAVER API HUB (Application Services > NAVER API HUB > Application 등록)
    naver_api_hub_client_id: str = ""
    naver_api_hub_client_secret: str = ""
    naver_api_hub_base_url: str = "https://naverapihub.apigw.ntruss.com"

    # SENS 문자 (Application Services > Simple & Easy Notification Service)
    sens_sms_service_id: str = ""
    sens_sms_from: str = ""

    def allows_origin(self, origin: str) -> bool:
        """이 서버를 불러도 되는 앱 주소인지 (CORS 와 네이버 로그인 뒤 돌려보낼 주소가 같은 기준을 쓴다)."""
        if origin in self.cors_origins:
            return True
        return bool(self.cors_origin_regex and re.fullmatch(self.cors_origin_regex, origin))


settings = Settings()
