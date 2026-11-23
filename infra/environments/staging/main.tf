terraform {
  required_version = ">= 1.7.0, < 2.0.0"

  required_providers {
    ncloud = {
      source  = "NaverCloudPlatform/ncloud"
      version = "= 4.0.7"
    }
  }
}

provider "ncloud" {
  region      = "KR"
  support_vpc = true
}

variable "deployment" {
  type = object({
    primary_zone           = string
    secondary_zone         = optional(string)
    app_image_number       = string
    login_key_name         = string
    app_spec_code          = optional(string)
    app_disk_size          = optional(number)
    operator_ipv4_cidrs    = set(string)
    public_landing         = optional(bool, false)
    public_demo            = optional(bool, false) # true: 앱·시연 자리 HTTPS를 모든 IP에 연다 (SSH는 운영자만)
    bucket_suffix          = string
    db_image_product_code  = string
    db_product_code        = string
    db_engine_version_code = string
    db_storage_encryption  = optional(bool, false)
  })
}

variable "db_admin_password" {
  type      = string
  sensitive = true
  nullable  = false
}

variable "ssh_private_key_path" {
  description = "VM 인증키(.pem) 경로. null이면 앱 릴리스를 올리지 않는다."
  type        = string
  default     = null
}

module "donna" {
  source = "../../modules/donna"

  environment       = "staging"
  deployment        = var.deployment
  db_admin_password = var.db_admin_password

  release = var.ssh_private_key_path == null ? null : {
    ssh_private_key_path = pathexpand(var.ssh_private_key_path)
    app_env_path         = "${path.module}/app.env"
    api_base_url         = "same-origin" # 웹을 연 주소로 API 를 부른다 (시연 자리 :8441 … 마다 다른 백엔드)
    demo_seats           = 4             # 동시 시연 자리: https://staging.donna.ai.kr:8441 ~ :8444
    web_dev_tools        = true          # 팀 전용 staging 에서 /demo·/dev 시연 화면을 연다
    caddyfile            = "staging.Caddyfile"
    caddy_sites          = var.deployment.public_landing ? ["landing.Caddyfile"] : []
  }
}

output "release_id" {
  value = module.donna.release_id
}

output "deployment" {
  value = module.donna.deployment
}

output "storage" {
  value = module.donna.storage
}
