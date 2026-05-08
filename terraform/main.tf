data "aws_vpc" "default" {
  default = true
}

data "aws_caller_identity" "current" {}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Si on cible une instance existante, on la lit ici (au lieu de la créer).
data "aws_instance" "existing" {
  count       = var.existing_instance_id != "" ? 1 : 0
  instance_id = var.existing_instance_id
}

# Ubuntu 20.04 LTS (Canonical) – filtre simple.
# Si var.ami_id est fourni, il est utilisé à la place.
data "aws_ami" "ubuntu_2004" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  effective_ami_id = var.ami_id != "" ? var.ami_id : data.aws_ami.ubuntu_2004.id
}

# Security group dédié stack Sotipapier (8000 / 8001 / 8002) + SSH — seulement si EC2 créée par Terraform.
resource "aws_security_group" "agi" {
  count = var.existing_instance_id == "" ? 1 : 0
  # Le champ "name" doit être unique par VPC. On utilise donc un name_prefix + suffix généré.
  name_prefix = "${var.name}-sg-"
  description = "Sotipapier: SSH + APIs 8000 (PDR) 8001 (MP/CHIMIE) 8002 (recette)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH administration"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  dynamic "ingress" {
    for_each = [8000, 8001, 8002]
    content {
      description = "Sotipapier API port ${ingress.value}"
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = var.open_ports_cidrs
    }
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name}-sg-instance-b-tools"
  }
}

locals {
  user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail

    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release git

    # Docker Engine
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list

    apt-get update
    apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    systemctl enable docker
    systemctl start docker

    # Add ubuntu user to docker group
    usermod -aG docker ubuntu || true

    mkdir -p /home/ubuntu/projet_industriel_agi
    chown -R ubuntu:ubuntu /home/ubuntu/projet_industriel_agi
  EOT
}

resource "aws_instance" "agi" {
  count                       = var.existing_instance_id == "" ? 1 : 0
  ami                         = local.effective_ami_id
  instance_type               = var.instance_type
  key_name                    = var.key_name
  vpc_security_group_ids      = [aws_security_group.agi[0].id]
  subnet_id                   = data.aws_subnets.default.ids[0]
  associate_public_ip_address = true

  user_data = local.user_data

  lifecycle {
    prevent_destroy = true
  }

  root_block_device {
    volume_size = 120
    volume_type = "gp3"
  }

  tags = {
    Name = var.name
  }
}

# Résolution d’hôte pour le déploiement (instance existante OU nouvelle)
locals {
  target_instance_id = var.existing_instance_id != "" ? var.existing_instance_id : aws_instance.agi[0].id
  target_public_ip   = var.existing_instance_id != "" ? data.aws_instance.existing[0].public_ip : aws_instance.agi[0].public_ip
}

# Instance existante : ouvrir 8000/8001/8002 sur les SG attachés (si manage_existing_instance_sg_ingress = true).
# Si ces règles existent déjà dans la console AWS → erreur Duplicate : laisser la variable à false (défaut).
locals {
  existing_sg_ids_for_rules = var.existing_instance_id != "" ? tolist(data.aws_instance.existing[0].vpc_security_group_ids) : []
  tool_api_ports            = [8000, 8001, 8002]
  existing_sg_port_pairs = flatten([
    for sg in local.existing_sg_ids_for_rules : [
      for p in local.tool_api_ports : { sg_id = sg, port = p }
    ]
  ])
}

resource "aws_security_group_rule" "existing_tools_ingress" {
  for_each = var.manage_existing_instance_sg_ingress && var.existing_instance_id != "" ? {
    for pair in local.existing_sg_port_pairs :
    "${pair.sg_id}_${pair.port}" => pair
  } : {}

  type              = "ingress"
  from_port         = each.value.port
  to_port           = each.value.port
  protocol          = "tcp"
  cidr_blocks       = var.open_ports_cidrs
  security_group_id = each.value.sg_id
  description       = "Sotipapier API port ${each.value.port}"
}

# Services à démarrer après copie (agent-pdr sauté si train async + start agent-pdr, comme avant)
locals {
  up_agent_pdr = var.deploy_start_agent_pdr && !(var.deploy_train_agent_pdr && var.deploy_train_agent_pdr_async)
  compose_up_services = compact(concat(
    local.up_agent_pdr ? ["agent-pdr"] : [],
    var.deploy_start_agent_classification ? ["agent-classification"] : [],
    var.deploy_start_agent_recette ? ["agent_recette"] : [],
  ))
  compose_up_services_str = join(" ", local.compose_up_services)
}

# Commandes de déploiement (évite la complexité des quotes dans inline)
locals {
  # IMPORTANT: on force un rebuild pour prendre les nouvelles dépendances et le nouveau code.
  train_cmd = var.deploy_train_agent_pdr ? (
    var.deploy_train_agent_pdr_async ?
    "docker compose build --no-cache agent-pdr-train && docker compose --compatibility up -d --force-recreate agent-pdr-train && echo TRAIN_STARTED_IN_BACKGROUND && docker compose ps agent-pdr-train" :
    "docker compose build --no-cache agent-pdr-train && docker compose --compatibility up --abort-on-container-exit --exit-code-from agent-pdr-train agent-pdr-train"
  ) : "echo skip_agent_pdr_train"
  compose_build_cmd = "docker compose build --no-cache agent-pdr agent-classification agent_recette"
}

locals {
  deploy_compose_enabled = var.ssh_private_key_path != "" && var.project_src_dir != ""
  rsync_exclude_cli      = join(" ", [for p in var.deploy_rsync_excludes : format("--exclude=%s", p)])
  # Script distant commun (après upload rsync ou file)
  deploy_post_upload_script = <<-REMOTE
bash -lc '
  set -euxo pipefail
  APP_DIR="${var.remote_deploy_dir}"
  if [ ! -f "$APP_DIR/docker-compose.yml" ] && [ -f "$APP_DIR/${basename(var.project_src_dir)}/docker-compose.yml" ]; then
    APP_DIR="$APP_DIR/${basename(var.project_src_dir)}"
  fi
  test -f "$APP_DIR/docker-compose.yml" || (echo "ERROR: docker-compose.yml not found in $APP_DIR" && exit 2)
  sudo chown -R ${var.ssh_user}:${var.ssh_user} "${var.remote_deploy_dir}"

  sudo mkdir -p /etc/docker
  sudo tee /etc/docker/daemon.json >/dev/null <<'"'"'JSON'"'"'
{
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
JSON
  sudo systemctl restart docker
  sleep 3
  cd "$APP_DIR"
  docker compose config 2>/dev/null | grep -qiE "nvidia|capabilities:.*gpu" \
    || (echo "ERROR: docker-compose.yml doit réserver le GPU (nvidia) pour agent-pdr" && exit 2)
  docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu20.04 nvidia-smi >/dev/null \
    || (echo "ERROR: Docker GPU runtime unavailable (nvidia-container-toolkit/runtime issue)" && exit 2)

  if [ "${var.deploy_train_agent_pdr}" = "true" ]; then
    if [ -f data/pdr_train.csv ]; then
      echo "using data/pdr_train.csv"
    else
      test -f "data_sources/piece_de_rechange_data/ECA_PDR_31122023_Raw(AutoRecovered).csv.xlsx" \
        || (echo "ERROR: missing data_sources/piece_de_rechange_data/ECA_PDR_31122023_Raw(AutoRecovered).csv.xlsx" && exit 2)
      test -f "data_sources/Data_Produc_Qual/RATIOS STANDARDS.csv.xlsx" \
        || (echo "ERROR: missing data_sources/Data_Produc_Qual/RATIOS STANDARDS.csv.xlsx" && exit 2)
    fi
  fi

  ${local.train_cmd}
  ${local.compose_build_cmd}
  if [ "${var.deploy_train_agent_pdr}" = "true" ] && [ "${var.deploy_train_agent_pdr_async}" = "true" ] && [ "${local.up_agent_pdr}" = "false" ]; then
    echo "Note: agent-pdr non démarré (train async + démarrage API PDR reporté). Démarrer manuellement après le train : docker compose up -d agent-pdr"
  fi
  if [ -n "${local.compose_up_services_str}" ]; then
    docker compose --compatibility up -d --force-recreate ${local.compose_up_services_str}
  else
    echo "Aucun service compose sélectionné (deploy_start_*). Build effectué."
  fi
'
REMOTE
}

# Copie rsync (défaut) : exclusions, delta, moins de risque de timeout que le provisioner file.
resource "null_resource" "deploy_compose_rsync" {
  count = local.deploy_compose_enabled && var.deploy_use_rsync ? 1 : 0

  triggers = {
    instance_id    = local.target_instance_id
    project_src    = var.project_src_dir
    exclude_digest = join("|", var.deploy_rsync_excludes)
  }

  connection {
    type        = "ssh"
    host        = local.target_public_ip
    user        = var.ssh_user
    private_key = file(var.ssh_private_key_path)
    timeout     = var.ssh_connection_timeout
  }

  provisioner "remote-exec" {
    inline = [
      "bash -lc 'sudo mkdir -p ${var.remote_deploy_dir} && sudo chown -R ${var.ssh_user}:${var.ssh_user} ${var.remote_deploy_dir}'",
    ]
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-CMD
set -euo pipefail
command -v rsync >/dev/null || { echo "Erreur: installez rsync (ex: sudo apt install rsync)"; exit 1; }
rsync -az --partial --human-readable \
  ${local.rsync_exclude_cli} \
  -e "ssh -i ${var.ssh_private_key_path} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 -o ServerAliveCountMax=240" \
  "${trimsuffix(var.project_src_dir, "/")}/" \
  "${var.ssh_user}@${local.target_public_ip}:${var.remote_deploy_dir}/"
CMD
  }

  provisioner "remote-exec" {
    inline = [local.deploy_post_upload_script]
  }

  depends_on = [
    aws_instance.agi,
    data.aws_instance.existing,
    aws_security_group_rule.existing_tools_ingress,
  ]
}

# Repli : provisioner file Terraform (tout le dossier, sans exclusion — lent si local_models présent).
resource "null_resource" "deploy_compose_scp" {
  count = local.deploy_compose_enabled && !var.deploy_use_rsync ? 1 : 0

  triggers = {
    instance_id = local.target_instance_id
    project_src = var.project_src_dir
  }

  connection {
    type        = "ssh"
    host        = local.target_public_ip
    user        = var.ssh_user
    private_key = file(var.ssh_private_key_path)
    timeout     = var.ssh_connection_timeout
  }

  provisioner "remote-exec" {
    inline = [
      "bash -lc 'sudo mkdir -p ${var.remote_deploy_dir} && sudo chown -R ${var.ssh_user}:${var.ssh_user} ${var.remote_deploy_dir}'",
    ]
  }

  provisioner "file" {
    source      = var.project_src_dir
    destination = var.remote_deploy_dir
  }

  provisioner "remote-exec" {
    inline = [local.deploy_post_upload_script]
  }

  depends_on = [
    aws_instance.agi,
    data.aws_instance.existing,
    aws_security_group_rule.existing_tools_ingress,
  ]
}