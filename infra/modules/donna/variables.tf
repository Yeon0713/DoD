variable "environment" {
  type = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Use staging or production."
  }
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

  validation {
    condition = (
      length(var.deployment.operator_ipv4_cidrs) > 0 &&
      alltrue([for cidr in var.deployment.operator_ipv4_cidrs : can(cidrnetmask(cidr)) && !endswith(cidr, "/0")])
    )
    error_message = "Set one or more operator IPv4 CIDRs. Public /0 access is not allowed for SSH or staging HTTPS."
  }

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,19}[a-z0-9]$", var.deployment.bucket_suffix))
    error_message = "Use a 3–21 character account-specific bucket suffix made of lowercase letters, numbers, and hyphens."
  }

  validation {
    condition = (
      can(regex("^[0-9]+$", var.deployment.app_image_number)) &&
      alltrue([
        for value in [
          var.deployment.primary_zone,
          var.deployment.login_key_name,
          var.deployment.db_image_product_code,
          var.deployment.db_product_code,
          var.deployment.db_engine_version_code
        ] : trimspace(value) != "" && !startswith(value, "REPLACE_")
      ])
    )
    error_message = "Fill in the NCP zone, numeric KVM image number, login key name and PostgreSQL catalog values."
  }
}

variable "db_admin_password" {
  type      = string
  sensitive = true
  nullable  = false

  validation {
    condition = (
      can(regex("^[!-~]{8,20}$", var.db_admin_password)) &&
      can(regex("[a-zA-Z]", var.db_admin_password)) &&
      can(regex("[0-9]", var.db_admin_password)) &&
      can(regex("[^a-zA-Z0-9]", var.db_admin_password)) &&
      !strcontains(lower(var.db_admin_password), "donnaadmin") &&
      alltrue([
        for forbidden in ["`", "&", "+", "\\", "\"", "'", "/"] : !strcontains(var.db_admin_password, forbidden)
      ])
    )
    error_message = "Use 8–20 ASCII characters including a letter, a digit, and a supported symbol. The password cannot contain the database administrator ID."
  }
}
