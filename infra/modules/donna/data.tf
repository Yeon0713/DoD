resource "ncloud_postgresql" "app" {
  service_name                 = "${local.prefix}-db"
  server_name_prefix           = "${local.prefix}-db"
  vpc_no                       = ncloud_vpc.this.id
  subnet_no                    = ncloud_subnet.this["database"].id
  secondary_subnet_no          = one(ncloud_subnet.database_secondary[*].id)
  user_name                    = "donnaadmin"
  user_password                = var.db_admin_password
  client_cidr                  = "${local.app_private_ip}/32"
  database_name                = "donna"
  image_product_code           = var.deployment.db_image_product_code
  product_code                 = var.deployment.db_product_code
  engine_version_code          = var.deployment.db_engine_version_code
  storage_encryption           = var.deployment.db_storage_encryption
  ha                           = local.production
  multi_zone                   = local.production ? true : null
  backup                       = true
  automatic_backup             = true
  backup_file_retention_period = 14

  lifecycle {
    prevent_destroy = true
  }
}

resource "ncloud_access_control_group_rule" "database" {
  access_control_group_no = one(ncloud_postgresql.app.access_control_group_no_list)

  inbound {
    protocol                       = "TCP"
    source_access_control_group_no = ncloud_access_control_group.app.id
    port_range                     = "5432"
  }

  lifecycle {
    # Cloud DB adds its own self-referencing rules. Applying the complete rule set
    # again would remove those managed rules.
    ignore_changes = [inbound, outbound]

    postcondition {
      condition = anytrue([
        for rule in self.inbound : rule.protocol == "TCP" && rule.port_range == "5432" &&
        rule.source_access_control_group_no == ncloud_access_control_group.app.id
      ])
      error_message = "The managed database ACG must allow PostgreSQL from the app ACG."
    }
  }
}

removed {
  from = ncloud_objectstorage_bucket.this
  lifecycle {
    destroy = false
  }
}
