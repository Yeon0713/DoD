# DONNA NCP Terraform 호스팅 계획

기준일은 2026년 11월 22일입니다. **네이버 클라우드 플랫폼(NCP) 한국 리전 VPC**, **Cloud DB for PostgreSQL**, **Ncloud Storage**를 사용합니다. 1차 배포 대상은 공개 랜딩 페이지, DONNA v0.2.1 사장님·알바생 웹 앱, 음성 백엔드입니다. 계획은 현재 `main`과 작업 트리의 `landing/`을 기준으로 하며, 실제 배포 SHA, NCP 계정, 월 예산은 배포 준비 단계에서 확정합니다.

## 1. 초기 구성

```text
브라우저 ── HTTPS / WSS ── 도메인 → NCP Public IP
                                     │
                              NCP Server · 한국 리전
                              └─ Caddy
                                 ├─ donna.ai.kr → 랜딩 정적 파일
                                 ├─ app.donna.ai.kr → Expo 웹 번들
                                 └─ app.donna.ai.kr API → systemd / FastAPI :8100
                                     ├─ 사설 VPC → Cloud DB for PostgreSQL
                                     └─ HTTPS → Ncloud Storage → Meta가 게시용 JPEG 조회

CI → Ncloud Storage 배포 버킷 → VM 릴리스
Cloud Insight → 서버·DB 지표 및 경보
```

| 구성 | 초기 결정 |
|---|---|
| 네트워크 | 환경별 VPC에 앱용 퍼블릭 서브넷과 DB용 프라이빗 서브넷을 둡니다. 앱 ACG는 `80/443`을 공개하고 관리 접속은 승인된 VPN 또는 관리 IP로 제한합니다. `8100`은 호스트 루프백에만 바인딩합니다. DB는 사설 접속 주소를 사용하고 DB ACG의 `5432`는 앱 ACG에서만 허용합니다. 마이그레이션도 VPC 내부에서 실행합니다. |
| 앱 서버 | 환경당 Linux x86_64 인스턴스 1대로 시작합니다. 운영 VM의 Caddy가 TLS를 종료하고 호스트 이름별로 랜딩과 Expo 정적 파일을 제공합니다. FastAPI는 Python 가상환경의 Uvicorn 워커 1개를 systemd에서 실행합니다. |
| DB | 검증 환경은 단일 Cloud DB 인스턴스를 사용하고 운영 환경은 관리형 Multi-Zone HA를 사용합니다. 선택한 이미지의 스토리지 암호화 지원, 자동 백업, TLS 접속과 장애 조치 시 재연결을 확인합니다. |
| DNS·배포 | NCP Global DNS에서 도메인의 A 레코드를 해당 환경의 공인 IP에 연결합니다. 백엔드 릴리스 압축 파일, 랜딩 정적 파일, Expo 웹 번들과 릴리스 명세는 배포용 Ncloud Storage 버킷에 커밋 SHA별로 저장합니다. |
| 운영 환경 | 접근 제한된 staging에는 초옹장 시연 데이터와 시험용 인스타 계정을 둡니다. production은 별도 DB·버킷·자격증명으로 구성하고 인증과 복구 검증 뒤 실제 매장에 엽니다. |

PostgreSQL을 도입해도 현재 음성 API 프로세스가 예약 작업 스레드를 띄우고 프로세스 내부 락으로 실행을 제어합니다. 작업 선점과 외부 게시 중복 방지가 검증될 때까지 배포 중에도 작업 실행 프로세스는 하나로 유지합니다. 가입·매장 등록에 재사용하는 `server/app` 코드는 서버 릴리스에 포함하고, 첫 버전 앱·목업 서버·개발 대시보드는 공개 대상에서 제외합니다. [음성 서버](../server/voice/main.py) · [작업 큐](../server/voice/jobs/queue.py) · [NCP PostgreSQL ACG 설정](https://guide.ncloud-docs.com/docs/en/clouddbforpostgresql-start)

### 인스턴스별 권장 사양

| 환경 | 인스턴스 | 수량 | vCPU / RAM (대당) | 스토리지 |
|---|---|---:|---|---|
| Staging | 앱 서버, High CPU g3 (`c2-g3`) | 1 | 2 vCPU / 4 GB | SSD 30 GB |
| Staging | Cloud DB for PostgreSQL, Standard 단일 | 1 | 2 vCPU / 8 GB | 관리형 SSD, 초기 데이터 용량 10 GB |
| Production | 앱 VM 이름 `c16-g2-h100` | 1 | CPU형 16 vCPU / 32 GB 권장 | SSD 100 GB |
| Production | Cloud DB for PostgreSQL, Standard g3 Multi-Zone HA | 2 (Primary 1 + Secondary 1) | 각 4 vCPU / 16 GB | g3 상품의 기본 데이터 스토리지, 초기 10 GB부터 자동 증가. 비용 산정 기준 100 GB |

운영 DB의 Primary와 장애 조치용 Secondary는 서로 다른 Zone의 프라이빗 서브넷에 둡니다. NCP가 DB 생성 시 데이터 스토리지 10 GB를 할당하고, 사용량에 따라 10 GB 단위로 자동 확장합니다. **100 GB는 운영 용량과 비용을 계산하는 기준**이며 프로비저닝 값은 NCP의 자동 확장 방식을 따릅니다. 데이터·인덱스·백업 사용량을 별도로 관측하고 운영 데이터 이관 전 자동 확장을 검증합니다. 앱 서버는 한 대로 시작하므로 앱 장애나 배포 중에는 접속이 중단될 수 있습니다. [NCP Server 상품 사양](https://api.ncloud-docs.com/docs/get-product-spec) · [서버 스토리지 설정](https://guide.ncloud-docs.com/docs/server-create-vpc) · [Cloud DB 용량과 HA 설정](https://guide.ncloud-docs.com/docs/clouddbforPostgreSQL-PostgreSQLserver) · [PostgreSQL g3 스토리지 및 Multi-Zone](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs/resources/postgresql)

두 환경을 모두 띄우면 앱 VM 2대와 관리형 DB 노드 3대입니다. Expo 웹과 FastAPI는 같은 앱 VM에서 실행합니다. Ncloud Storage, Global DNS, 공인 IP는 관리형 리소스로 별도 VM을 할당하지 않습니다. Terraform 적용 전 한국 리전의 선택한 Zone과 OS 이미지에서 앱 사양을 조회하고, PostgreSQL 엔진 버전과 HA 조합의 상품 코드를 확인합니다. [NCP 서버 사양 데이터 소스](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs/data-sources/server_specs) · [NCP PostgreSQL 상품 조회](https://api.ncloud-docs.com/docs/en/database-vpostgresql-getcloudpostgresqlproductlist)


### 운영 VM 사양 확인

Terraform의 `ncloud_server.name`은 `c16-g2-h100`으로 설정합니다. 실제 하드웨어는 계정의 NCP 콘솔이나 API에서 확인한 사양 코드 또는 상품 코드로 지정하며, 이름에 들어간 문자열로 서버 세대나 GPU 유무를 판단하지 않습니다. 새 VM의 권장 사양은 CPU형 16 vCPU·32 GB이며, 공개 사양에 나온 `c16-g3`가 한 가지 선택입니다. 선택한 Zone과 OS 이미지에서 생성 가능한 실제 상품을 확인한 뒤 Terraform 입력을 고정합니다. [Terraform NCP 서버 리소스](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs/resources/server) · [NCP 서버 상품 사양](https://api.ncloud-docs.com/docs/get-product-spec)

Expo 웹은 빌드된 파일을 브라우저에 전달하고, FastAPI는 CLOVA Speech·Voice·Studio와 OpenAI 이미지 API를 호출합니다. 현재 이 경로들은 VM의 GPU를 사용하지 않습니다. CPU와 RAM 여유는 동시 접속과 로컬 이미지 처리에 도움이 될 수 있습니다. 외부 AI 응답 시간과 현재 작업 큐 처리량은 따로 측정합니다. [음성 인식](../server/voice/stt.py) · [CLOVA Studio 호출](../server/Harness/clova_tools.py) · [포스터 이미지 엔진](../server/app/poster_ai/image_engine.py)

### 웹과 음성 연결

| 주소 | 제공할 서비스 | 대상 서버 |
|---|---|---|
| `https://donna.ai.kr` | 공개 소개·시연 랜딩 페이지 | 운영 전까지 검증 VM, 운영 전환 후 운영 VM |
| `https://app.donna.ai.kr` | 사장님·알바생 Expo 웹과 음성 API. 알바생 진입점은 `/staff` | 운영 VM |
| `https://staging.donna.ai.kr` | 팀 전용 검증 앱과 음성 API | 검증 VM |

- 랜딩은 HTML·CSS·이미지로 구성돼 별도 빌드가 필요 없습니다. `landing/index.html`, CSS 파일, `landing/assets/`를 정적 산출물로 배포합니다. Caddy에서 랜딩과 Expo에 서로 다른 문서 루트를 사용합니다. 랜딩 도메인에서는 정적 파일만 제공하므로 FastAPI가 중지돼도 같은 VM의 Caddy가 실행 중이면 페이지를 열 수 있습니다. [랜딩 소스](../landing/index.html) · [Caddy 정적 파일 서빙](https://caddyserver.com/docs/caddyfile/directives/file_server)
- 랜딩의 기존 시연 영상 버튼에는 실제 영상 URL이 필요합니다. 운영 앱을 공개할 때 랜딩에 `https://app.donna.ai.kr`로 가는 앱 링크를 추가합니다.
- `donna-voice/app`에서 `npm ci`, `npm run typecheck`, `npx expo export --platform web`을 실행합니다. 빌드에 `EXPO_PUBLIC_API_BASE_URL=https://<환경별-도메인>`을 넣습니다.
- Caddy는 앱 도메인에서만 `/v1`, `/api`, `/health`, `/static`, `/media`를 백엔드로 보내고, `/staff` 등 Expo 앱 경로는 `index.html`로 연결합니다. 개발 경로 차단을 먼저 평가하고 API 오류 상태는 그대로 반환합니다. [Caddy 경로 처리](https://caddyserver.com/docs/caddyfile/directives/handle)
- 실기기에서 HTTPS 마이크 권한과 `wss://<도메인>/v1/stt/stream` 연결·재접속을 확인합니다. staging 접근 제한도 WebSocket에 적용합니다. [Expo 웹 배포](https://docs.expo.dev/guides/publishing-websites/) · [Caddy 자동 HTTPS](https://caddyserver.com/docs/automatic-https) · [음성 클라이언트](../donna-voice/app/src/lib/voice.ts)

### 실제 도메인 연결

**`donna.ai.kr`의 위임을 확인했습니다.** 2026년 11월 22일 공개 DNS 조회에서 NCP 네임서버 두 개를 확인했습니다. 운영 전까지 루트 도메인은 검증 VM에서 공개 랜딩을 제공하고, Caddy는 검증 호스트의 HTTPS 접근을 운영자 IP로 제한합니다. [공개 랜딩 배포](../infra/README.md#검증-vm의-공개-랜딩)

Terraform으로 NCP 공인 IP를 만들고, 도메인의 A 레코드를 그 IP로 연결할 수 있습니다. 도메인 구매·갱신은 등록기관에서 관리합니다. 기존 DNS를 유지하면 네임서버 변경 없이 레코드만 추가하면 됩니다. NCP Global DNS로 DNS 관리 주체를 옮길 경우 등록기관에서 NCP가 안내한 네임서버로 위임해야 합니다. [NCP 공인 IP 리소스](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs/resources/public_ip) · [NCP Global DNS 설정 순서](https://guide.ncloud-docs.com/docs/globaldns-procedure)

1. 운영 전환 시 루트 `donna.ai.kr`와 `app.donna.ai.kr`의 A 레코드를 같은 운영 VM 공인 IPv4에 연결합니다. `staging.donna.ai.kr`는 검증 VM 공인 IPv4에 연결합니다. Terraform의 환경별 공인 IP 출력을 DNS 적용 단계에 전달합니다.
2. **NCP Global DNS를 쓸 경우**, 현재 공식 `ncloud` Provider 문서에서 Global DNS 영역·레코드 리소스를 확인할 수 없습니다. 공인 IP는 Terraform으로 관리하고, 레코드는 NCP 콘솔에서 적용하거나 Global DNS API의 조회·변경·적용 절차를 CI 단계로 자동화합니다. 자동화는 지정한 호스트의 레코드만 변경하며, 적용 결과가 실제 DNS에 반영됐는지 확인합니다. 기존 영역을 이관할 경우 메일·소유권 검증 등 기존 레코드를 먼저 복제한 뒤 네임서버를 변경합니다. [공식 NCP Provider](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs) · [NCP 레코드 관리](https://guide.ncloud-docs.com/docs/globaldns-record) · [NCP 레코드 적용 API](https://api.ncloud-docs.com/docs/networking-globaldns-record-applydomain)
3. `dig`으로 세 호스트가 대상 공인 IP를 가리키는지 확인합니다. Caddy의 TLS 발급·갱신과 HTTPS 전환을 확인한 뒤, 루트에서 랜딩과 이미지·CSS가 열리는지, 앱 서브도메인에서 `/staff`·API·음성 WebSocket이 동작하는지 확인합니다. 운영 앱의 `EXPO_PUBLIC_API_BASE_URL`과 `VOICE_APP_ORIGINS`에는 `https://app.donna.ai.kr`를 사용합니다. 네이버 로그인 콜백은 `https://app.donna.ai.kr/api/auth/naver/callback`으로 설정합니다. [Caddy 자동 HTTPS](https://caddyserver.com/docs/automatic-https)

## 2. SQLite에서 PostgreSQL로 전환

| 현재 데이터 | 이전 계획 |
|---|---|
| `voice.db` | `docs`, 카운터, 알바생·초대·할 일·출퇴근 테이블을 옮깁니다. 매장 설정, 대화, 리뷰, 감사, 작업 큐, 인스타 게시 상태와 기존 식별자를 보존합니다. 직원 비밀번호 해시는 유지하고, 기존 세션은 새 환경 진입 시 재로그인하도록 처리합니다. |
| `registry.db`, `db/data/<매장>.db`, `common.db`, 지역 날씨 DB | 매장 등록·소유권·예약과 매장별 업무 데이터를 옮깁니다. SQLite의 매장 파일 연결 구조를 PostgreSQL의 `store_id` 기반 테이블과 매장별 조회 조건으로 바꿉니다. 공통 이벤트·날씨는 별도 공통 테이블에 둡니다. 실제로 보유한 운영 데이터만 가져오고 시연 데이터는 staging에 입력합니다. |
| 하네스 추적·CLOVA 사용량·캐시·평가 | 운영에 사용하는 감사·추적·사용량의 이전 범위와 보존 기간을 확정합니다. 재생성 가능한 캐시는 비운 상태로 시작하고, 테스트 계정과 오프라인 평가 DB는 production에 가져오지 않습니다. 운영 경로에 필요한 추적·사용량 저장소도 PostgreSQL이나 운영 로그로 전환합니다. |
| 포스터와 게시용 미디어 | 파일은 Ncloud Storage로 옮기고 PostgreSQL에는 객체 키와 게시 상태를 저장합니다. 앱 미리보기 등 계속 사용해야 할 로컬 포스터 경로를 조사해, 파일을 먼저 복사하고 DB 참조를 전환합니다. |

### 스키마와 애플리케이션 변경

1. 기존 SQLAlchemy를 활용해 PostgreSQL 엔진을 연결하고, `psycopg`와 Alembic을 도입합니다. 스키마 변경 전용 계정과 런타임 계정을 분리하고 `DATABASE_URL`은 런타임에 주입합니다. NCP 접속 가이드와 인증서에 맞춰 TLS 및 서버 인증서 검증을 staging에서 확인합니다. 마이그레이션은 앱 시작과 별개의 단일 배포 단계에서 실행합니다.
2. `voice/repo.py`와 `staff_db.py`의 직접 SQLite 호출을 전환합니다. 문서 데이터는 초기에는 기존 구조를 유지하는 `JSONB`로 옮기고 매장·종류 인덱스를 둡니다. `rowid` 정렬은 명시적 정렬 키로 대체하고 원본 순서를 보존합니다. `INSERT OR REPLACE`·`INSERT OR IGNORE`는 충돌 정책을 확인해 PostgreSQL upsert로 전환합니다. 거래 단위, 날짜·시간대, 카운터 원자 갱신을 검증합니다.
3. `db/session.py`의 SQLite `ATTACH` 및 파일 탐색을 제거하고, 매장 데이터와 등록 데이터가 같은 매장 ID를 유지하도록 이관합니다. 네이버 OAuth 임시 상태를 다중 인스턴스에서도 써야 하는 시점에는 만료가 있는 공유 저장소로 옮깁니다.
4. production 설정에서 PostgreSQL 접속 실패 시 배포를 실패시킵니다. SQLite를 쓰는 로컬 도구와 평가 코드는 별도 설정으로 실행하고, 운영 요청 경로에서 SQLite 파일이 생기지 않는지 확인합니다. [음성 저장소](../server/voice/repo.py) · [알바생 저장소](../server/voice/staff_db.py) · [매장 데이터 엔진](../server/db/session.py) · [매장 등록 저장소](../server/app/data_pipeline/registered_stores.py)

### 데이터 전환과 복구

1. staging에서 같은 스냅샷을 두 번 가져와도 중복이 생기지 않는 이관 스크립트를 만듭니다. 테이블·매장·문서 유형별 건수, 대표 레코드, 참조 무결성, 시퀀스 다음 값, 시각·한글 값, 미디어 참조를 대조합니다. 브리핑·답글 수정·알바생 완료·감사 이력이 양쪽에서 같은 결과를 내는지 확인합니다.
2. 운영 데이터가 있으면 전환 창을 잡아 쓰기 요청과 작업 큐를 중단하고 일관된 SQLite 백업을 남깁니다. 처리 중이던 게시 작업은 DB와 인스타 상태를 대조합니다. 업로드 파일과 데이터를 이관한 뒤 점검이 끝날 때까지 새 환경의 외부 게시 작업을 정지합니다. 새 환경에 가져올 운영 데이터가 없다면 빈 PostgreSQL을 스키마 마이그레이션으로 초기화합니다.
3. 건수 비교와 주요 흐름 확인을 마친 뒤 앱을 PostgreSQL로 연결하고 단일 워커를 켭니다. 새 DB에 쓰기를 열기 전에는 기존 환경으로 복귀할 수 있습니다. 전환 후에는 PostgreSQL을 기준 데이터로 유지하고 호환되는 앱 버전으로 복귀합니다. 이후 SQLite로 돌아가야 한다면 전환 뒤 발생한 쓰기를 대조·재이관하는 절차를 먼저 검증합니다.
4. Cloud DB 자동 백업을 활성화하고 서비스가 지원하는 보존 기간 안에서 일일 백업 14일과 초기 복구 목표 **데이터 손실 최대 24시간·복구 2시간 이내**를 검토합니다. 복원은 별도 DB 인스턴스에서 연습합니다. DB 복원 뒤 지속 보관 대상 객체 참조와 대기 작업까지 확인하고, 게시 작업은 인스타 상태와 대조한 뒤 재개합니다. [NCP PostgreSQL 백업·복원](https://guide.ncloud-docs.com/docs/en/clouddbforpostgresql-backup)

## 3. 인스타 사진을 Ncloud Storage로 전환

### 버킷과 운영 용량

한국 리전 `kr`의 Ncloud Storage를 사용합니다. 버킷에 디스크 용량을 미리 할당할 필요가 없으며 저장량, API 요청 수, 네트워크 전송량을 기준으로 과금됩니다. 운영 미디어는 **합계 50 GB를 초기 비용 산정 기준**으로 잡고, 운영을 시작한 뒤 저장량과 외부 다운로드 전송량으로 조정합니다. 50 GB는 미디어 예산 산정용이며 배포 산출물과 백업 사용량은 별도로 집계합니다. [Ncloud Storage 용량·과금](https://guide.ncloud-docs.com/docs/ncloudstorage-spec)

| 버킷 용도 | 구성 |
|---|---|
| 인스타 게시용 JPEG | 검증·운영용 각각 1개. 비공개로 두고 Meta에 만료형 조회 URL을 전달합니다. 게시용 복사본은 최초 7일 보존을 목표로 하되, 큐 재시도 기간보다 짧아지지 않도록 검증합니다. |
| 앱 원본·미리보기 | 검증·운영용 각각 1개. 앱에서 계속 참조하는 파일을 비공개로 보관하고, 게시용 복사본의 삭제 정책과 분리합니다. |
| 배포 산출물 | 검증·운영용 비공개 버킷. 서버 릴리스, 랜딩 정적 파일, Expo 번들과 릴리스 명세를 저장하고 이전 릴리스로 복귀할 때 사용합니다. |
| 운영 백업 | 전용 비공개 버킷. 별도로 내보내는 DB 덤프와 미디어 복구 자료가 있을 때 보관합니다. Cloud DB 자동 백업은 관리형 백업에서 확인합니다. |

### 게시 경로 전환

앱은 `MEDIA_HOST=ncloud_storage`에서 JPEG를 게시 전용 비공개 버킷에 올리고, Meta에 한 시간짜리 SigV4 조회 URL을 전달합니다. Ncloud Storage는 버킷 정책으로 접근을 제어합니다. [현재 미디어 코드](../server/voice/instagram/media.py) · [게시 작업](../server/voice/instagram/posts.py) · [Ncloud Storage API](https://api.ncloud-docs.com/docs/storage-ncloudstorage)

| 설정 | 값 |
|---|---|
| `MEDIA_HOST` | `ncloud_storage` |
| `NCLOUD_STORAGE_BUCKET` | 환경별 인스타 게시 전용 버킷 이름 |
| `NCLOUD_STORAGE_ENDPOINT` | `https://kr.ncloudstorage.com` |
| `NCLOUD_STORAGE_REGION` | `kr` |
| `NCLOUD_STORAGE_ACCESS_KEY`, `NCLOUD_STORAGE_SECRET_KEY` | 앱 전용 키입니다. 둘 다 비어 있으면 기존 NCP 인증값을 사용합니다. 배포에서는 게시 버킷에 업로드·조회 권한만 부여합니다. |

1. Terraform이 출력한 버킷 이름으로 별도 스크립트가 staging과 production의 Ncloud Storage 버킷을 생성합니다. 배포 산출물, 앱 미리보기용 미디어, 백업은 별도 저장 위치를 사용합니다. 버킷과 객체의 기본 접근 권한은 비공개로 구성합니다.
2. 게시 시점에 JPEG를 `instagram/<store_id>/<post_id>/<파일명>.jpg`에 `Content-Type: image/jpeg`로 업로드합니다. 객체 키는 재시도에서 재사용하고, Meta에 전달하는 조회 URL은 컨테이너 생성 직전에 발급합니다. Meta에는 발급 직후 URL을 전달하고 서명된 주소를 게시 기록이나 오류 로그에 남기지 않습니다. 컨테이너·게시물 ID를 써서 재시도를 조정하는 작업은 운영 파일럿 전에 검증합니다.
3. 외부에서 접근 가능한 HTTPS 주소를 앱 인증 없이 Meta가 읽을 수 있는지 확인합니다. staging에서 비서명 주소의 접근 거부, 서명 주소의 JPEG 응답, 만료, 실제 피드와 스토리 게시를 확인합니다. 기본 만료 시간은 한 시간이며, Meta 컨테이너 처리와 큐 재시도 시간을 실측합니다. Meta가 서명 URL을 읽지 못하면 게시 전용 경로에서 앱이 단기 조회를 중계하는 방식을 검토합니다. 버킷 목록·원본·미리보기는 비공개로 유지합니다. [Meta 게시 API](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/) · [Ncloud Storage API 인증](https://api.ncloud-docs.com/docs/storage-ncloudstorage)
4. 업로드 실패, URL 만료, 컨테이너 생성 뒤 재시작, 게시 요청의 응답 시간 초과를 검사합니다. 게시 여부가 불명확하면 기존 컨테이너·게시물 상태를 먼저 대조하고 같은 게시물을 다시 발행하지 않습니다. NCP 실패 시 작업을 보류하거나 재시도하며 Litterbox로 자동 전환하지 않습니다.
5. 게시 전용 복사본에는 재시도 기간보다 긴 보존 기간을 적용합니다. 게시 버킷에 콘솔에서 수명 주기 정책을 설정합니다. 앱에서 계속 사용하는 이미지에는 게시용 삭제 정책을 적용하지 않습니다. 기존 게시물은 재게시하지 않고, 전환 시점에 대기 중인 게시만 원본으로부터 새 URL을 만듭니다. [Ncloud Storage 수명 주기](https://guide.ncloud-docs.com/docs/ncloudstorage-datamanagement)

현재 인스타 토큰은 시연 매장 중심입니다. Ncloud Storage 전환은 사진 전달 경로를 바꾸는 작업입니다. 실제 고객 매장으로 게시를 넓히기 전에 매장별 OAuth, 발행 권한, 토큰 만료·해지를 검증합니다. [현재 인스타 설정](../donna-voice/README.md#인스타-연결)

## 4. Terraform과 배포 자동화

현재 Terraform은 `infra/environments/staging/`와 `infra/environments/production/`에 있습니다. 두 루트에 공통 NCP 모듈을 연결하고 도메인별 DNS 레코드와 Ncloud Storage 버킷 이름을 출력합니다. 첫 plan 입력값과 현재 구현 범위는 [Terraform 실행 안내](../infra/README.md)에 정리했습니다.

| 경로 | 관리 대상 |
|---|---|
| `infra/bootstrap/` | 원격 상태 접근 권한, CI용 NCP 자격증명과 환경 경계 초기화. 상태 저장소는 앱보다 먼저 구성합니다. |
| `infra/environments/staging/`, `infra/environments/production/` | VPC·서브넷·ACG·서버·공인 IP·PostgreSQL 및 Ncloud Storage 버킷 설정 출력. DNS 레코드는 DNS 사업자의 Terraform Provider 또는 NCP Global DNS 콘솔·API로 관리합니다. 모니터링은 Provider 지원 범위에 따라 관리합니다. |
| `infra/modules/donna_host/`, `infra/modules/donna_data/` | 앱 서버·네트워크 구성과 DB·스토리지 구성. 환경마다 DB, 버킷, 상태, 키를 분리합니다. |

- 공식 `NaverCloudPlatform/ncloud` Provider를 사용하고 버전을 고정합니다. 핵심 리소스는 `ncloud_vpc`, `ncloud_subnet`, `ncloud_server`, `ncloud_public_ip`, `ncloud_postgresql`입니다. DB 교체·삭제가 계획에 나타나면 적용 전에 데이터 이전 및 복구 경로를 확인합니다. [NCP Provider](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs) · [PostgreSQL 리소스](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs/resources/postgresql)
- Ncloud Storage는 공식 Provider의 기존 Object Storage 리소스와 별개로 준비합니다. `storage` 출력을 [버킷 준비 스크립트](../infra/provision_ncloud_storage.py)에 넘깁니다. 이 단계는 버킷이 이미 있으면 재사용합니다.
- Terraform 상태 저장소는 암호화, 버전 복구, 동시 실행 잠금, 환경별 접근 제어를 갖춥니다. 관리형 원격 상태 서비스 사용이 가능하면 HCP Terraform을 기본안으로 검토합니다. 상태도 NCP에만 보관해야 한다면 전용 비공개 버킷에서 S3 백엔드의 초기화·잠금·버전 복원을 먼저 검증한 뒤 채택합니다. HashiCorp의 S3 백엔드는 Amazon S3를 대상으로 검증되므로 NCP 호환을 전제하지 않습니다. [HCP Terraform 상태](https://developer.hashicorp.com/terraform/cloud-docs/workspaces/state) · [Terraform S3 백엔드 지원 범위](https://developer.hashicorp.com/terraform/language/backend/s3)
- Provider의 `ncloud_postgresql`은 관리자 비밀번호 인자를 요구합니다. 선택한 버전에서 비밀번호가 plan·state에 남는지 확인합니다. 일반 인자로 관리해야 하면 상태와 plan을 비밀 데이터로 취급하고 접근을 제한합니다. 상태에 비밀번호 저장이 금지된 환경이면 DB 초기 생성·비밀번호 회전은 관리 절차로 분리하고, Terraform import 후 plan에서 의도치 않은 교체나 비밀번호 재주입이 없는지 검증합니다. 앱 DB 비밀번호와 Meta·CLOVA 키는 배포 시 런타임 비밀로 주입합니다. [PostgreSQL Provider 사양](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs/resources/postgresql) · [Terraform 민감 정보 관리](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)
- CI에서 `terraform fmt -check`, `validate`, `plan`을 실행하고 검토한 변경만 적용합니다. 앱 배포에서는 같은 커밋의 서버 릴리스 압축 파일과 웹 번들을 함께 고정합니다. VM에 릴리스별 디렉터리와 Python 가상환경을 준비하고, 잠금 파일 기준으로 의존성을 설치합니다. 릴리스 경로를 전환한 뒤 systemd로 FastAPI를 재시작합니다. 실패하면 호환되는 직전 릴리스 경로를 복구합니다. 이전 워커 중지 → DB 백업 및 단일 스키마 마이그레이션 → 새 앱 기동 → DB·API·큐 확인 순서로 배포합니다. GitHub 호스티드 러너에서 관리 포트를 열 필요가 없도록, 승인된 관리 경로를 통해 배포를 실행합니다.
- 랜딩은 별도 릴리스 경로로 배포합니다. 랜딩 파일만 바뀌면 현재 정적 파일 경로만 전환하고 Expo·FastAPI 재배포 없이 반영합니다.

## 5. 공개 순서와 완료 기준

| 순서 | 작업 | 완료 기준 |
|---|---|---|
| 1 | NCP staging과 배포 파이프라인 구축 | 앱이 HTTPS·WSS로 동작하고 DB는 앱 네트워크에서만 접속됩니다. 같은 구성으로 실행한 Terraform plan에 의도치 않은 변경이 없습니다. |
| 2 | PostgreSQL 전환 리허설 | 실제와 같은 표본으로 데이터 대조, 기존 ID 보존, 재시작, 별도 인스턴스 복원을 통과합니다. 운영 경로가 SQLite 파일 없이 시작합니다. |
| 3 | 인스타 미디어 전환 리허설 | NCP 버킷에서 전달된 JPEG로 시험 계정 피드·스토리 게시를 확인합니다. 재시작·재시도에서 중복 게시가 없고 Litterbox 호출이 없습니다. |
| 4 | 실제 매장 공개 준비 | 사장님·알바생 세션과 매장별 권한을 검증합니다. 운영에서 `/v1/dev/*`, 목업 로그인, 테스트 계정, 개발 대시보드와 API 문서를 차단하고 `VOICE_DEMO_FIXTURE=`, `DEMO_STORE_DATA=false`를 확인합니다. 네이버 콜백 URL과 음성 API의 세션·Origin·호출 제한도 검증합니다. |
| 5 | production 파일럿 | 루트 도메인에서 공개 랜딩이 열리고 앱 서브도메인의 링크·HTTPS가 동작합니다. PostgreSQL로 전환한 뒤 데이터·대기 작업을 대조합니다. DB 오류, 디스크·메모리, 큐 지연, 외부 API 오류에 대한 경보와 복구 담당자가 정해져 있습니다. 앱과 DB 복구를 연습한 뒤 공개합니다. |

매장 데이터 접근 여부는 세션과 매장 소속으로 서버에서 판단합니다. 기존 홈·대화 API와 인스타 연결·게시 경로에서 매장 ID를 바꾼 요청을 검증하고, 사장님 로그인과 매장 가입은 실제 검증된 경로만 엽니다. 음성, 리뷰 원문, 토큰, 로그인 티켓, 만료형 URL은 기본 운영 로그에서 제외합니다. 현재 외부 리뷰 답글 게시가 미연동인 점도 파일럿 범위에 반영합니다. [홈 API](../server/voice/api/home.py) · [대화 API](../server/voice/api/turn.py) · [남은 기능](../donna-voice/docs/open-features.md)

## 6. 비용과 확장 기준

NCP 요금 계산기로 환경별 Server, Public IP, 관리형 PostgreSQL과 HA 구성, DB 백업, Ncloud Storage 요청·전송량과 모니터링을 비교합니다. CLOVA Speech·Voice·Studio와 AI 포스터 호출량은 별도로 산정합니다. 운영 지표는 Cloud Insight와 애플리케이션 로그로 확인합니다. [NCP 요금 계산기](https://www.ncloud.com/charge/calc/ko) · [Cloud Insight](https://guide.ncloud-docs.com/docs/en/cloudinsight-cloudinsightoverview)

큐 적체나 서비스 중단이 허용 범위를 넘으면 API와 작업 프로세스를 분리합니다. PostgreSQL 트랜잭션을 사용하는 작업 선점·만료·복구와 외부 게시 중복 방지를 검증한 뒤 워커나 앱 인스턴스를 늘립니다.
