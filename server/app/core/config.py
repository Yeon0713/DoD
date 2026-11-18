import re

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """server/.env 에서 읽어오는 설정 값. 없으면 아래 기본값을 쓴다."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DoD API"
    # 서버를 부를 수 있는 웹 주소. 8082 는 mobile/ 앱을 웹으로 켠 주소, 3000 은 예전 frontend/
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8082", "http://127.0.0.1:8082"]
    # 위 목록(CORS_ORIGINS)에 있는 주소만 받는다. 목록 밖 주소를 더 받아야 할 때만 .env 에 CORS_ORIGIN_REGEX 를 적는다 (기본은 비움)
    cors_origin_regex: str = ""

    # 로그인이 생기기 전까지 보여 줄 가게. 주소에 ?store_id=s002 를 붙이면 그 가게를 보여 준다
    demo_store_id: str = "s001"
    # 분석과 계획을 다시 계산하는 간격(분). 그 사이에는 계산해 둔 결과를 그대로 쓴다
    snapshot_refresh_minutes: int = 10
    # 로컬 시험용: /dev/clock 으로 서버 시계를 앞당길 수 있게 한다. 배포에서는 켜지 않는다
    dev_clock_enabled: bool = False
    # 로컬 시험용: 개발자 대시보드(dev/ 폴더, http://localhost:8000/dev-dashboard/)와 그 API(/api/dev_tools)를 연다.
    # 모든 가게 데이터와 AI 기록이 보이므로 배포에서는 켜지 않는다
    dev_tools_enabled: bool = False
    # 매장을 등록하면 우리 전용 목업 주문·매출·알바 데이터를 그 가게 파일에 넣는다 (POS·배달앱 연동 전 시연용)
    demo_store_data: bool = True

    # 네이버 아이디로 로그인 (developers.naver.com 에 등록한 애플리케이션). 데모 시험 모드에서 쓴다
    naver_login_client_id: str = ""
    naver_login_client_secret: str = ""
    # 네이버 개발자 센터에 적은 Callback URL 과 글자 하나까지 같아야 한다
    naver_login_callback_url: str = "http://localhost:8000/api/auth/naver/callback"
    # 카드 문장을 CLOVA X 로 사장님 말투로 다듬을지. 키가 없으면 켜 있어도 원래 문장을 쓴다
    sentence_polish_enabled: bool = True
    # LLM 기능(답글 초안, 반복 불만, 메뉴판·포스터)을 에이전트 하네스(server/Harness)로 돌릴지. false 면 예전 단일 호출만.
    # 개발자 대시보드 '에이전트' 탭에서 바꿀 수 있다 (서버를 다시 켜면 이 값으로 돌아간다)
    agent_harness_enabled: bool = False

    # 네이버 클라우드 API (콘솔 > 마이페이지 > 인증키 관리). SENS 도 이 키를 쓴다.
    ncloud_access_key: str = ""
    ncloud_secret_key: str = ""

    # HyperCLOVA X (CLOVA Studio > API 키)
    voice_stt: bool = False
    voice_tts: bool = True
    clova_voice_client_id: str = ""
    clova_voice_client_secret: str = ""
    # 받아 적기를 CLOVA Speech 단문 인식으로 (voice/stt.py). 비어 있으면 CSR. 단문 인식 도메인 > 빌더 > 설정 > 연동 정보의 Secret Key
    clova_speech_secret_key: str = ""
    # CLOVA Speech 키워드 부스팅: 잘 듣게 할 단어, 쉼표로 구분 (3글자 이상, 한국어만). CSR 은 "도나야"를 "누나야"로 적는다
    voice_stt_boostings: str = "도나야"
    clova_studio_api_key: str = ""
    clova_studio_base_url: str = "https://clovastudio.stream.ntruss.com"
    clova_studio_model: str = "HCX-005"
    clova_studio_timeout: float = 30
    # CLOVA 토큰 단가(원, 1,000 토큰당, VAT 별도). 네이버 클라우드 CLOVA Studio 요금표를 보고 넣는다.
    # 0 이면 개발자 대시보드에 '단가 미설정'으로 보이고 비용은 0원으로 센다
    clova_price_input_per_1k: float = 0
    clova_price_output_per_1k: float = 0
    # 에이전트 평가(server/Harness/evals)의 CLOVA X 심판 모델. 답글 검토기(CLOVA_STUDIO_MODEL)와 다른 모델을 쓴다. 서버 기능은 쓰지 않는다
    eval_judge_model: str = "HCX-007"

    # AI 포스터 그림 (app/poster_ai). openai: OpenAI 이미지 API(OPENAI_API_KEY, 그림 한 장마다 요금).
    # codex: 이 컴퓨터에 ChatGPT 계정으로 로그인한 Codex CLI 의 그림 만들기(구독제, API 키 없음). mock: 받은 사진으로 그림만 합친다 (시험용, 글자 없음)
    poster_image_engine: str = "openai"
    openai_api_key: str = ""
    poster_openai_model: str = "gpt-image-2"
    poster_openai_quality: str = "medium"  # low | medium | high (높을수록 비싸고 글자가 또렷하다)
    poster_openai_size: str = "1024x1536"  # 세로 2:3. 스토리(9:16)로는 to_story 가 맞춘다
    codex_bin: str = "codex"  # Codex CLI 실행 파일 (PATH 에 없으면 전체 경로)
    poster_image_timeout: float = 300  # 그림 하나에 기다리는 초

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

    # 기상청 API허브 인증키 (apihub.kma.go.kr > 마이페이지). 비어 있으면 등록한 가게도 공통 목업 날씨를 쓴다 (app/weather)
    kma_api_key: str = ""

    # 인스타그램 (Instagram API with Unified Login, graph.facebook.com. 음성 백엔드 server/voice/instagram). 실제 OAuth 전이라 시연 가게 하나만 잇는다.
    # 토큰은 앱 대시보드 'API setup with Unified login' 의 Generate access tokens 에서 받는다 (instagram_basic, instagram_content_publish)
    instagram_access_token: str = ""
    instagram_user_id: str = ""  # IG 프로페셔널 계정 id (GET /me/assigned_instagram_accounts?fields=id,username)
    instagram_graph_version: str = "v23.0"
    # 인스타가 사진을 가져갈 공개 주소. base_url: PUBLIC_MEDIA_BASE_URL(ngrok 등) 아래 /media 로 내보낸다.
    # object_storage: NCP Object Storage 버킷에 올린다 (키는 NCLOUD_ACCESS_KEY / NCLOUD_SECRET_KEY)
    # litterbox: 테스트용. litterbox.catbox.moe 에 1시간짜리 공개 주소로 올린다
    media_host: str = "base_url"
    public_media_base_url: str = ""
    ncp_object_storage_bucket: str = ""
    ncp_object_storage_endpoint: str = "https://kr.object.ncloudstorage.com"
    ncp_object_storage_region: str = "kr-standard"

    def allows_origin(self, origin: str) -> bool:
        """이 서버를 불러도 되는 앱 주소인지 (CORS 와 네이버 로그인 뒤 돌려보낼 주소가 같은 기준을 쓴다)."""
        if origin in self.cors_origins:
            return True
        return bool(self.cors_origin_regex and re.fullmatch(self.cors_origin_regex, origin))


settings = Settings()
