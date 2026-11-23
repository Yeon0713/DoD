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

module "donna" {
  source = "../../modules/donna"

  environment       = "production"
  deployment        = var.deployment
  db_admin_password = var.db_admin_password
}

output "deployment" {
  value = module.donna.deployment
}

output "storage" {
  value = module.donna.storage
}
