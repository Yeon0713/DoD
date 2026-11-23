locals {
  storage = {
    endpoint = "https://kr.ncloudstorage.com"
    region   = "kr"
    buckets = {
      for purpose in(local.production ? toset(["releases", "media", "instagram", "backups"]) : toset(["releases", "media", "instagram"])) :
      purpose => "${local.prefix}-${purpose}-${var.deployment.bucket_suffix}"
    }
  }
}

output "storage" {
  description = "Ncloud Storage bucket names to pass to the separate provisioning step."
  value       = local.storage
}

output "deployment" {
  description = "Non-secret connection information and DNS A records for the deployment step."
  value = {
    app_server_id    = ncloud_server.app.id
    app_name         = ncloud_server.app.name
    app_public_ipv4  = ncloud_public_ip.app.public_ip
    app_private_ipv4 = local.app_private_ip
    dns_a_records = {
      for host in(local.production ? toset(["donna.ai.kr", "app.donna.ai.kr"]) : setunion(
        toset(["staging.donna.ai.kr"]),
        var.deployment.public_landing ? toset(["donna.ai.kr"]) : toset([])
      )) :
      host => ncloud_public_ip.app.public_ip
    }
    postgresql = {
      id       = ncloud_postgresql.app.id
      database = ncloud_postgresql.app.database_name
      port     = ncloud_postgresql.app.port
      private_domain = one([
        for server in ncloud_postgresql.app.postgresql_server_list : server.private_domain
        if contains(["A", "M"], server.server_role)
      ])
    }
    object_storage = local.storage
  }
}
