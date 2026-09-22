# Charge backend on Oracle Cloud Always Free: one VM running Caddy (TLS),
# PocketBase (accounts + storage) and the Charge API, via docker compose.
# Separate from ReBind's VM so the two apps never compete for RAM.
#
#   cd infra/oracle && terraform init && terraform apply
#
# Auth comes from ~/.oci/config (profile DEFAULT). The tenancy is the compartment.

terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
  }
}

provider "oci" {
  config_file_profile = "DEFAULT"
}

variable "tenancy_ocid" {
  type = string
}

# Always Free A1. This tenancy allows 2 cores in AD-1 and AD-3 (0 in AD-2); 1 OCPU / 6 GB is
# enough for Charge and far easier to get when London is short of capacity.
variable "shape" {
  type    = string
  default = "VM.Standard.A1.Flex"
}

variable "ocpus" {
  type    = number
  default = 1
}

variable "memory_gbs" {
  type    = number
  default = 6
}

# London has three ADs on some tenancies and one on others; A1 capacity varies by AD.
variable "ad_index" {
  type    = number
  default = 0
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/charge_oracle_ed25519.pub"
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "ubuntu" {
  compartment_id           = var.tenancy_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = var.shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

# The tenancy is at its VCN limit, so the VM joins ReBind's VCN and public subnet
# (its security list already opens 22/80/443). The VM itself is separate.
data "oci_core_vcns" "shared" {
  compartment_id = var.tenancy_ocid
  display_name   = "rebind-vcn"
}

data "oci_core_subnets" "shared" {
  compartment_id = var.tenancy_ocid
  vcn_id         = data.oci_core_vcns.shared.virtual_networks[0].id
}

resource "oci_core_instance" "charge" {
  compartment_id      = var.tenancy_ocid
  display_name        = "charge-backend"
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[var.ad_index].name
  shape               = var.shape

  dynamic "shape_config" {
    for_each = var.shape == "VM.Standard.A1.Flex" ? [1] : []
    content {
      ocpus         = var.ocpus
      memory_in_gbs = var.memory_gbs
    }
  }

  create_vnic_details {
    subnet_id        = data.oci_core_subnets.shared.subnets[0].id
    assign_public_ip = true
    hostname_label   = "charge-backend"
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu.images[0].id
    boot_volume_size_in_gbs = 50
  }

  metadata = {
    ssh_authorized_keys = file(pathexpand(var.ssh_public_key_path))
    user_data           = base64encode(file("${path.module}/cloud-init.yaml"))
  }

  lifecycle {
    ignore_changes = [source_details, metadata]
  }
}

output "public_ip" {
  value = oci_core_instance.charge.public_ip
}

output "hostname" {
  value = "${replace(oci_core_instance.charge.public_ip, ".", "-")}.sslip.io"
}
