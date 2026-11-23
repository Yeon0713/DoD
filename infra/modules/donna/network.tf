locals {
  production = var.environment == "production"
  prefix     = "donna-${var.environment}"
  vpc_cidr   = local.production ? "10.72.0.0/16" : "10.71.0.0/16"

  subnets = {
    app = {
      cidr = cidrsubnet(local.vpc_cidr, 8, 1)
      zone = var.deployment.primary_zone
      type = "PUBLIC"
    }
    database = {
      cidr = cidrsubnet(local.vpc_cidr, 8, 2)
      zone = var.deployment.primary_zone
      type = "PRIVATE"
    }
  }

  app_private_ip = cidrhost(local.subnets.app.cidr, 10)
  https_cidrs    = (local.production || var.deployment.public_landing) ? toset(["0.0.0.0/0"]) : var.deployment.operator_ipv4_cidrs
}

resource "ncloud_vpc" "this" {
  name            = local.prefix
  ipv4_cidr_block = local.vpc_cidr

  lifecycle {
    precondition {
      condition = !local.production || (
        try(trimspace(var.deployment.secondary_zone), "") != "" &&
        var.deployment.secondary_zone != var.deployment.primary_zone
      )
      error_message = "Production requires a PostgreSQL secondary zone different from the primary zone."
    }
  }
}

resource "ncloud_subnet" "this" {
  for_each = local.subnets

  name           = "${local.prefix}-${each.key}"
  vpc_no         = ncloud_vpc.this.id
  network_acl_no = ncloud_vpc.this.default_network_acl_no
  subnet         = each.value.cidr
  zone           = each.value.zone
  subnet_type    = each.value.type
  usage_type     = "GEN"
}

resource "ncloud_subnet" "database_secondary" {
  count = local.production ? 1 : 0

  name           = "${local.prefix}-database-ha"
  vpc_no         = ncloud_vpc.this.id
  network_acl_no = ncloud_vpc.this.default_network_acl_no
  subnet         = cidrsubnet(local.vpc_cidr, 8, 3)
  zone           = var.deployment.secondary_zone
  subnet_type    = "PRIVATE"
  usage_type     = "GEN"
}

resource "ncloud_access_control_group" "app" {
  name   = "${local.prefix}-app"
  vpc_no = ncloud_vpc.this.id
}

resource "ncloud_access_control_group_rule" "app" {
  access_control_group_no = ncloud_access_control_group.app.id

  # The HTTP listener only serves ACME HTTP-01 and HTTPS redirects.
  inbound {
    protocol   = "TCP"
    ip_block   = "0.0.0.0/0"
    port_range = "80"
  }

  dynamic "inbound" {
    for_each = local.https_cidrs
    content {
      protocol   = "TCP"
      ip_block   = inbound.value
      port_range = "443"
    }
  }

  dynamic "inbound" {
    for_each = var.deployment.operator_ipv4_cidrs
    content {
      protocol   = "TCP"
      ip_block   = inbound.value
      port_range = "22"
    }
  }

  # 시연 자리(https://<환경>.donna.ai.kr:8441 …)는 public_demo가 아니면 운영자만 연다 (release.tf demo_seats)
  dynamic "inbound" {
    for_each = local.demo_seats > 0 ? (var.deployment.public_demo ? toset(["0.0.0.0/0"]) : var.deployment.operator_ipv4_cidrs) : toset([])
    content {
      protocol   = "TCP"
      ip_block   = inbound.value
      port_range = local.demo_seats == 1 ? "8441" : "8441-${8440 + local.demo_seats}"
    }
  }

  # The VM needs outbound package downloads, DNS, time sync, and provider APIs.
  dynamic "outbound" {
    for_each = toset(["53", "80", "443"])
    content {
      protocol   = "TCP"
      ip_block   = "0.0.0.0/0"
      port_range = outbound.value
    }
  }

  outbound {
    protocol   = "TCP"
    ip_block   = local.vpc_cidr
    port_range = "5432"
  }

  outbound {
    protocol   = "UDP"
    ip_block   = "0.0.0.0/0"
    port_range = "53"
  }

  outbound {
    protocol   = "UDP"
    ip_block   = "0.0.0.0/0"
    port_range = "123"
  }
}

resource "ncloud_network_interface" "app" {
  name                  = "${local.prefix}-app"
  subnet_no             = ncloud_subnet.this["app"].id
  private_ip            = local.app_private_ip
  access_control_groups = [ncloud_access_control_group.app.id]
}
