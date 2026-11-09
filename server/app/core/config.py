from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """server/.env 에서 읽어오는 설정 값. 없으면 아래 기본값을 쓴다."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DoD API"
    cors_origins: list[str] = ["http://localhost:3000"]

    # PostgreSQL (로컬은 docker-compose.yml 값)
    database_url: str = "postgresql+psycopg://dod:dod@localhost:5432/dod"

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


settings = Settings()
