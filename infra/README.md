# DONNA NCP Terraform

한국 리전에서 검증과 운영 인프라를 별도로 관리합니다. 검증은 앱 VM과 PostgreSQL 각 1대, 운영은 앱 VM 1대와 PostgreSQL Multi-Zone HA 1세트입니다. 운영 VM 이름은 `c16-g2-h100`이며 기본 사양은 CPU형 `c16-g3`입니다. Global DNS 레코드의 대상 IP와 이름은 출력으로 제공합니다. [배포 계획](../docs/terraform-hosting-plan.md)

| 환경 | Terraform 경로 | 도메인 |
|---|---|---|
| 검증 | `environments/staging` | `staging.donna.ai.kr`, 운영 전까지 공개 랜딩 `donna.ai.kr` |
| 운영 | `environments/production` | `donna.ai.kr`, `app.donna.ai.kr` |

## 첫 plan

1. NCP에서 Terraform 전용 Sub Account에 API Gateway 접근과 사용할 서비스 권한을 부여합니다. `NCLOUD_ACCESS_KEY`와 `NCLOUD_SECRET_KEY`는 실행 환경의 비밀로 주입합니다.
2. 환경별 `terraform.tfvars.example`을 같은 경로의 `terraform.tfvars`로 복사합니다. 운영자 공인 IPv4 CIDR, 기존 NCP 서버 인증키 이름, 사용 가능한 Linux x86_64 KVM 이미지 번호와 고유 버킷 접미사를 입력합니다. 같은 PostgreSQL 메이저 버전으로 검증의 G2 Standard 2 vCPU/8 GB와 운영의 G3 Standard 4 vCPU/16 GB 조합에서 각각 DB 이미지·상품·엔진 버전 코드를 확인해 넣습니다. 운영 DB 두 Zone은 서로 달라야 합니다. [NCP VM 이미지 조회](https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs/data-sources/server_image_numbers) · [PostgreSQL 상품 조회](https://api.ncloud-docs.com/docs/en/database-vpostgresql-getcloudpostgresqlproductlist)
3. 해당 환경의 DB 관리자 암호를 `TF_VAR_db_admin_password`로 주입합니다. Terraform 상태와 저장한 plan에는 비밀번호가 들어갈 수 있습니다. 팀에서 공유하기 전에 환경별 암호화·잠금이 있는 원격 상태를 설정합니다. 현재 두 루트는 각각 로컬 상태를 사용합니다. [Terraform 비밀 데이터](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)
4. 저장소 루트에서 검증 환경을 먼저 초기화하고 검토합니다.

```sh
terraform -chdir=infra/environments/staging init
terraform -chdir=infra/environments/staging validate
terraform -chdir=infra/environments/staging plan
```

검증 계획을 검토한 뒤 같은 디렉터리에서 `terraform apply`를 실행합니다. 운영은 운영 전용 인증 설정과 변수를 준비한 뒤 경로를 `infra/environments/production`으로 바꿔 진행합니다.

첫 적용 전에 한국 리전 콘솔에서 **Cloud Log Analytics**의 이용 상태를 확인합니다. Cloud DB 생성은 미이용 상태에서 거절될 수 있습니다. 중간에 실패한 경우 기존 Terraform 상태를 유지하고 plan을 다시 확인합니다. [Cloud DB 생성 안내](https://guide.ncloud-docs.com/docs/clouddbforpostgresql-postgresqlserver)

## 서버 없이 로그인 인증키 만들기

Ncloud CLI 인증을 설정한 뒤 한국 리전에 검증용 서버 인증키를 먼저 만들 수 있습니다. 아래 명령은 서버와 VPC를 생성하지 않습니다. CLI를 설치한 디렉터리에서 실행하면 비공개 키가 로컬 `donna-staging.pem`에 저장됩니다. [Ncloud CLI 인증 설정](https://cli.ncloud-docs.com/docs/en/cli-auth) · [서버 인증키 생성 명령](https://cli.ncloud-docs.com/docs/cli-vserver-server-loginkey-createloginkey)

```sh
(
  umask 077
  set -C
  set -o pipefail
  ./ncloud vserver createLoginKey --regionCode KR --keyName donna-staging --output json |
    jq -er '.createLoginKeyResponse.privateKey | strings | select(length > 0)' > donna-staging.pem
)
```

발급 후 검증 환경의 `terraform.tfvars`에 `login_key_name = "donna-staging"`을 입력합니다. `.pem`은 저장소 밖의 접근이 제한된 위치에 보관합니다.

## 네트워크와 저장소

- 양쪽 환경의 SSH는 입력한 운영자 CIDR에서 접근합니다. 검증에서 `public_landing = true`를 설정하면 443번 포트를 공개하고 Caddy가 `staging.donna.ai.kr`의 모든 HTTPS 요청을 운영자 CIDR로 제한합니다. 80번 포트는 HTTP-01 인증과 HTTPS 리디렉션에 사용합니다. FastAPI는 루프백 주소에 바인딩합니다.
- PostgreSQL은 프라이빗 서브넷에 배치합니다. DB 계정의 허용 CIDR은 앱 VM 사설 IP 한 개이고, DB ACG의 5432는 앱 ACG에만 엽니다. 운영 HA는 별도 Zone의 Secondary를 사용합니다. 데이터 스토리지 유형은 선택한 DB 상품의 기본값을 사용합니다. NCP의 신규 DB 이미지에 따라 데이터 스토리지 암호화가 제공되지 않으므로 기본값은 꺼져 있습니다. 선택한 이미지에서 지원을 확인할 경우에만 `db_storage_encryption`을 켭니다. [NCP PostgreSQL DB Server 가이드](https://guide.ncloud-docs.com/docs/clouddbforPostgreSQL-PostgreSQLserver)
- PostgreSQL은 Terraform 삭제 방지가 적용됩니다. 과거 Object Storage 버킷이 Terraform 상태에 있다면 `removed` 블록이 실제 버킷을 지우지 않고 상태 관리만 종료합니다.
- Cloud DB ACG의 서비스 내부 규칙은 NCP가 관리합니다. Terraform은 최초 생성 시 앱의 PostgreSQL 접근 규칙을 추가하고 이후에는 해당 규칙이 유지되는지 확인합니다.

## Ncloud Storage 버킷 준비

Terraform 1.7 이상으로 인프라를 적용한 다음, 환경에 해당하는 `storage` 출력을 버킷 준비 스크립트에 전달합니다. 아래 예시는 검증용이며, Terraform에 사용한 NCP API 키가 현재 셸에 로드돼 있어야 합니다. [Ncloud Storage 버킷 생성 API](https://api.ncloud-docs.com/docs/ncloudstorage-createbucket)

```sh
terraform -chdir=infra/environments/staging output -json storage |
  server/.venv/bin/python infra/provision_ncloud_storage.py
```

스크립트는 필요한 버킷만 생성하고 기존 버킷이 있으면 재사용합니다. `--check`를 붙이면 존재 여부만 검사합니다. `instagram` 버킷을 백엔드의 `NCLOUD_STORAGE_BUCKET`으로 설정합니다. 환경별 배포·원본 미디어·인스타 게시 버킷을 분리하고, 운영에는 백업 버킷을 추가합니다. 게시용 복사본에만 콘솔에서 7일 수명 주기 규칙을 설정하고 재시도 기간이 충분한지 확인합니다. [인스타 설정](../donna-voice/README.md#인스타-연결) · [Ncloud Storage 수명 주기](https://guide.ncloud-docs.com/docs/ncloudstorage-datamanagement)

## 도메인과 앱 배포

```sh
terraform -chdir=infra/environments/staging output -json deployment
```

출력의 `dns_a_records`를 NCP Global DNS에 적용합니다. 검증에서 공개 랜딩을 활성화하면 루트 도메인과 검증 호스트가 검증 VM 공인 IP를 사용합니다. 운영 전환 시 루트 도메인과 `app` 호스트를 운영 VM 공인 IP로 연결합니다. NCP 콘솔의 **설정 적용 → 배포** 또는 별도의 Global DNS API 배포 단계에서 적용합니다. Terraform 루트는 DNS 레코드 변경을 호출하지 않습니다. [NCP Global DNS 적용](https://guide.ncloud-docs.com/docs/globaldns-record#설정-적용)

VM에는 별도 배포 단계에서 랜딩 정적 파일, Expo 웹 번들, Caddy 및 FastAPI systemd 서비스를 배치합니다. Terraform 출력에는 앱에 필요한 DB 사설 DNS 이름과 버킷 이름이 포함됩니다.

### 검증 VM의 공개 랜딩

1. [검증 Caddyfile](deploy/staging.Caddyfile)을 `/etc/caddy/Caddyfile`에 배치합니다. `/etc/caddy/donna-staging.env`에 `DONNA_STAGING_OPERATOR_CIDRS`를 공백으로 구분해 넣고 [systemd 드롭인](deploy/donna-staging-caddy.conf)을 `/etc/systemd/system/caddy.service.d/donna-staging.conf`에 설치합니다. CIDR은 Terraform의 `operator_ipv4_cidrs`와 같은 값으로 관리합니다.
2. 같은 환경 변수를 주입해 `caddy validate`를 실행한 뒤 Caddy에 적용합니다. 운영자 IP에서 검증 앱과 API에 접속하고, 허용 목록 외부에서 HTTPS 응답이 403인지 확인한 뒤 `public_landing = true`를 적용합니다.
3. `landing/`의 내용을 `/srv/donna/landing/releases/<릴리스>`에 배치하고 `/srv/donna/landing/current`를 해당 릴리스에 연결합니다. 루트 A 레코드를 배포하고 [랜딩 Caddyfile](deploy/landing.Caddyfile)을 `/etc/caddy/sites/landing.caddy`에 설치해 검증 후 Caddy를 리로드합니다.

### Terraform으로 앱까지 배포 (검증)

`ssh_private_key_path`를 주면 `terraform apply`가 인프라와 함께 앱도 올립니다. 서버 코드, Expo 웹 빌드, 랜딩, 환경변수, systemd·Caddy 설정이 포함됩니다. 주지 않으면 지금처럼 인프라만 다룹니다.

1. `environments/staging/app.env.example`을 `app.env`로 복사하고 서버용 값을 채웁니다. `VOICE_DATABASE_URL`을 포함해 서버에 필요한 값은 모두 여기에 둡니다. 이 파일은 git에 올라가지 않습니다.
2. 인증키 경로를 넣고 적용합니다. NCP VM은 SSH 키 접속을 받지 않으므로, Terraform이 이 키로 root 비밀번호를 조회(`ncloud_root_password`)해 접속합니다. 조회한 비밀번호는 로컬 Terraform 상태에 민감 값으로 남습니다.

```sh
set -a; . infra/.env; set +a
export TF_VAR_ssh_private_key_path=$PWD/personal_docs/ncp/donna-staging.pem
terraform -chdir=infra/environments/staging apply
```

- 소스(`server/`, `donna-voice/app/src`, `landing/`, `infra/deploy/`)나 `app.env`가 바뀌었을 때만 새 릴리스를 올립니다. 강제로 다시 올리려면 `-replace='module.donna.terraform_data.release[0]'`를 붙입니다.
- 로컬에서 [build_release.sh](deploy/build_release.sh)가 `release.tar.gz`를 만듭니다. git이 무시하는 `.env`, `db/app_data` 등은 빠집니다. 서버에서는 [install_release.sh](deploy/install_release.sh)가 `/srv/donna/releases/<ID>`에 풀고 `.venv`를 만든 뒤 `/srv/donna/current`를 바꾸고 서비스를 다시 시작합니다.
- 환경변수는 덮어쓰지 않고 합칩니다. `app.env`에 있는 키는 새 값으로 바뀌고, 서버에만 있는 키는 그대로 남습니다. 이전 파일은 `/etc/donna/staging.env.bak-<시각>`으로 남깁니다. 합친 결과에 `VOICE_DATABASE_URL`이 없으면 배포를 멈춥니다.
- 실행 중에 쓰는 파일은 `/srv/donna/shared`에 둡니다. `server/db/app_data`는 `shared/app_data`, `server/db/data`는 `shared/db_data`로 연결합니다. 저장소의 매장 DB는 릴리스의 `data.seed`에 두고 `shared/db_data`에 없을 때만 복사합니다.
- Caddy는 [staging.Caddyfile](deploy/staging.Caddyfile)을 `/etc/caddy/Caddyfile`로, [landing.Caddyfile](deploy/landing.Caddyfile)을 `/etc/caddy/sites/landing.caddy`로 둡니다. staging 접근을 허용하는 운영자 IP는 `operator_ipv4_cidrs`에서 가져와 `/etc/caddy/donna-staging.env`에 씁니다.
- `/health`가 60초 안에 응답하지 않으면 이전 릴리스로 되돌리고 apply를 실패로 끝냅니다. 릴리스는 최근 3개만 남깁니다.
- `app.env`는 파일로 올리므로 비밀값이 Terraform 상태에 남지 않습니다.

### 동시 시연 자리 (검증)

여러 사람이 같은 시간에 초옹장을 시연할 수 있게, 검증 VM에 자리마다 백엔드를 따로 띄웁니다. `environments/staging/main.tf`의 `demo_seats`(기본 4)로 자리 수를 정합니다.

| 자리 | 주소 | 백엔드 |
|---|---|---|
| 기본 | `https://staging.donna.ai.kr` | `donna-staging` (8100, PostgreSQL) |
| 1 ~ 4 | `https://staging.donna.ai.kr:8441` ~ `:8444` | `donna-staging-seat@1` ~ `@4` (8101 ~ 8104, SQLite) |

- 시계, 알림, 답글, 브리핑, "처음부터"가 자리마다 따로입니다. 각 자리에서 `/dev`의 "처음부터"를 누르면 그 자리만 처음 상태로 돌아갑니다.
- 자리 데이터는 `/srv/donna/seats/<자리>/`에 둡니다. [유닛](deploy/donna-staging-seat@.service)이 이 폴더를 코드가 쓰는 `shared/app_data`·`shared/db_data` 자리에 겹쳐 보입니다. 자리 백엔드는 `VOICE_DATABASE_URL`을 비워 SQLite를 씁니다.
- 웹은 하나의 빌드를 함께 쓰고, `EXPO_PUBLIC_API_BASE_URL=same-origin`으로 연 주소의 백엔드를 부릅니다.
- `public_demo = true`(현재 검증 설정)면 `staging.donna.ai.kr`과 8441~ 포트를 모든 IP에 엽니다. `/dev`와 API도 함께 공개됩니다. 끄면 운영자 CIDR에만 열고 Caddy도 운영자 IP만 허용합니다. SSH는 어느 쪽이든 운영자 CIDR만 받습니다. 자리를 줄이면 남는 자리 서비스는 끄고 데이터 폴더는 남깁니다.

### 검증 앱 릴리스

- 검증 배포에서 `https://staging.donna.ai.kr/`, `/staff`, `/health`, 초옹장 홈 API, 음성 WebSocket 연결을 확인했습니다. FastAPI는 앱 전용 DB 계정으로 `donna_voice` 스키마에 연결합니다.
- `staging.donna.ai.kr`의 A 레코드는 검증 VM의 공인 IPv4에 게시했습니다. Expo 웹 번들은 `EXPO_PUBLIC_API_BASE_URL=https://staging.donna.ai.kr`로 빌드합니다. VM에서는 [Caddy 설정](deploy/staging.Caddyfile)과 [FastAPI systemd 유닛](deploy/donna-staging.service)을 사용합니다.
- 릴리스 폴더에 `server/`, `web/`, Python `.venv/`를 두고 `/srv/donna/current`가 릴리스를 가리키게 합니다. `/etc/donna/staging.env`에는 앱 전용 `VOICE_DATABASE_URL`과 미디어 설정을 저장합니다. NCP DB 사용자 API에서 만든 앱 전용 역할에 `donna_voice` 스키마의 `USAGE`·`CREATE` 권한을 부여하면 systemd 시작 전 스키마 초기화가 실행됩니다.
- `VOICE_DATABASE_URL`은 음성 문서·대화·예약 작업과 알바생 데이터에 적용됩니다. 기존 매장 등록, 분석 데이터와 개발용 기록의 SQLite 전환은 별도 작업입니다. 이 검증 DB의 사설 접속 주소에서 TLS 협상을 지원하지 않는 것을 확인했습니다. 검증 접속은 VPC 내부 앱 ACG로 제한하고, 브라우저 접속은 Caddy HTTPS를 사용합니다.
