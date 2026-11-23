resource "ncloud_server" "app" {
  name                           = local.production ? "c16-g2-h100" : "donna-staging-app"
  subnet_no                      = ncloud_subnet.this["app"].id
  server_image_number            = var.deployment.app_image_number
  server_spec_code               = coalesce(var.deployment.app_spec_code, local.production ? "c16-g3" : "c2-g3")
  login_key_name                 = var.deployment.login_key_name
  base_block_storage_size        = coalesce(var.deployment.app_disk_size, local.production ? 100 : 30)
  base_block_storage_volume_type = "CB2"

  network_interface {
    network_interface_no = ncloud_network_interface.app.id
    order                = 0
  }

  depends_on = [ncloud_access_control_group_rule.app]
}

resource "ncloud_public_ip" "app" {
  server_instance_no = ncloud_server.app.id
  description        = "${local.prefix} public IPv4"
}
