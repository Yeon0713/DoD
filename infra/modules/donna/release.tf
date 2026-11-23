variable "release" {
  description = "앱 릴리스 배포 설정. null이면 Terraform이 VM에 앱을 올리지 않는다."
  type = object({
    ssh_private_key_path = string       # VM 인증키(.pem) 경로. 이 키로 root 비밀번호를 조회해 SSH 접속한다
    app_env_path         = string       # 서버 /etc/donna/<환경>.env 에 합칠 파일
    api_base_url         = string       # Expo 웹 빌드의 EXPO_PUBLIC_API_BASE_URL
    web_dev_tools        = bool         # Expo 웹 빌드의 EXPO_PUBLIC_DEV_TOOLS (/demo·/dev 시연 화면)
    caddyfile            = string       # /etc/caddy/Caddyfile 로 둘 infra/deploy 안의 파일
    caddy_sites          = list(string) # /etc/caddy/sites/<이름>.caddy 로 둘 파일들
    demo_seats           = number       # 동시 시연 자리 수 (자리 i: https://<환경>.donna.ai.kr:844i, 0~9)
  })
  default = null

  validation {
    condition     = var.release == null ? true : (var.release.demo_seats >= 0 && var.release.demo_seats <= 9 && floor(var.release.demo_seats) == var.release.demo_seats)
    error_message = "demo_seats 는 0~9 사이의 정수예요."
  }
}

locals {
  repo_root = abspath("${path.module}/../../..")

  # 이 파일들 중 하나라도 바뀌면 다음 apply 때 새 릴리스를 올린다.
  release_source_patterns = [
    "server/app/**", "server/voice/**", "server/Harness/**", "server/db/**", "server/requirements.txt",
    "donna-voice/app/src/**", "donna-voice/app/assets/**", "donna-voice/app/package.json",
    "donna-voice/app/package-lock.json", "donna-voice/app/app.json", "landing/**", "infra/deploy/**",
  ]
  release_source_files = var.release == null ? [] : sort([
    for f in toset(flatten([for p in local.release_source_patterns : fileset(local.repo_root, p)])) :
    f if !strcontains(f, "__pycache__") && !startswith(f, "server/db/app_data/") && !can(regex("^server/db/data/s1[0-9][0-9]\\.db$", f)) && !endswith(f, ".DS_Store")
  ])

  release_hash = var.release == null ? "" : sha256(join("\n", concat(
    [for f in local.release_source_files : "${f}:${filesha256("${local.repo_root}/${f}")}"],
    ["app.env:${filesha256(var.release.app_env_path)}", "api:${var.release.api_base_url}", "devtools:${var.release.web_dev_tools}", "caddy:${var.release.caddyfile}:${join(",", var.release.caddy_sites)}", "cidrs:${local.caddy_allow_cidrs}", "seats:${var.release.demo_seats}"]
  )))
  demo_seats = var.release == null ? 0 : var.release.demo_seats
  # Caddy가 앱에 허용하는 IP. public_demo면 모든 IP
  caddy_allow_cidrs = var.deployment.public_demo ? "0.0.0.0/0 ::/0" : join(" ", sort(var.deployment.operator_ipv4_cidrs))
  release_id        = substr(local.release_hash, 0, 12)
  release_dir       = "${local.repo_root}/infra/.build/${var.environment}"
}

# NCP VM 은 SSH 키 접속을 받지 않는다. 인증키로 root 비밀번호를 조회해 접속한다.
data "ncloud_root_password" "app" {
  count              = var.release == null ? 0 : 1
  server_instance_no = ncloud_server.app.id
  private_key        = file(var.release.ssh_private_key_path)
}

resource "terraform_data" "release" {
  count = var.release == null ? 0 : 1

  triggers_replace = {
    server  = ncloud_server.app.id
    release = local.release_hash
  }

  connection {
    type     = "ssh"
    host     = ncloud_public_ip.app.public_ip
    user     = "root"
    password = data.ncloud_root_password.app[0].root_password
    timeout  = "3m"
  }

  provisioner "local-exec" {
    command = "bash '${local.repo_root}/infra/deploy/build_release.sh' '${local.release_dir}' '${var.release.api_base_url}' '${var.release.web_dev_tools}'"
  }

  provisioner "remote-exec" {
    inline = ["rm -rf /tmp/donna-release && mkdir -p /tmp/donna-release"]
  }

  provisioner "file" {
    source      = "${local.release_dir}/release.tar.gz"
    destination = "/tmp/donna-release/release.tar.gz"
  }

  # source 로 올리면 비밀값이 Terraform 상태에 남지 않는다 (파일 해시만 남는다).
  provisioner "file" {
    source      = var.release.app_env_path
    destination = "/tmp/donna-release/app.env"
  }

  provisioner "file" {
    source      = "${local.repo_root}/infra/deploy" # 끝에 / 가 없으면 폴더째 /tmp/donna-release/deploy 로 올라간다
    destination = "/tmp/donna-release"
  }

  provisioner "remote-exec" {
    inline = [
      "bash /tmp/donna-release/deploy/install_release.sh '${var.environment}' '${local.release_id}' '${local.caddy_allow_cidrs}' '${var.release.caddyfile}' '${join(" ", var.release.caddy_sites)}' '${var.release.demo_seats}'",
    ]
  }
}

output "release_id" {
  description = "마지막으로 올린 앱 릴리스 ID (/srv/donna/releases/<ID>)."
  value       = var.release == null ? null : local.release_id
}
