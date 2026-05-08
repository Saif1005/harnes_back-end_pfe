data "aws_caller_identity" "current" {}

data "aws_instance" "orchestrator" {
  instance_id = var.orchestrator_instance_id
}

data "aws_subnet" "orchestrator_primary_subnet" {
  id = data.aws_instance.orchestrator.subnet_id
}

data "aws_subnets" "orchestrator_vpc_subnets" {
  filter {
    name   = "vpc-id"
    values = [data.aws_subnet.orchestrator_primary_subnet.vpc_id]
  }
}

resource "aws_security_group_rule" "orchestrator_http" {
  for_each = var.manage_security_group_rules ? toset(data.aws_instance.orchestrator.vpc_security_group_ids) : []

  type              = "ingress"
  from_port         = var.orchestrator_port
  to_port           = var.orchestrator_port
  protocol          = "tcp"
  cidr_blocks       = var.open_ports_cidrs
  security_group_id = each.value
  description       = "Cerveau orchestrateur FastAPI (terraform_cerveau)"
}

locals {
  public_ip = data.aws_instance.orchestrator.public_ip
  # Nom du dossier local (ex. cerveau_orchestrateur) — le provisioner file peut recréer ce sous-dossier sur la cible.
  cerveau_basename = basename(var.cerveau_src_dir)
  # Même convention que docker-compose (../data_sources depuis cerveau_orchestrateur/).
  data_sources_src = var.data_sources_src_dir != "" ? var.data_sources_src_dir : "${dirname(var.cerveau_src_dir)}/data_sources"
  # Hash de contenu pour forcer le redéploiement quand un fichier source change.
  source_files_hash = sha1(join(
    "",
    [for f in fileset(var.cerveau_src_dir, "**") : filesha256("${var.cerveau_src_dir}/${f}")]
  ))
  data_sources_hash = try(
    sha1(join("", [for f in fileset(local.data_sources_src, "**") : filesha256("${local.data_sources_src}/${f}")])),
    "no_local_data_sources"
  )
  db_password_effective = var.db_password != "" ? var.db_password : try(random_password.db_password[0].result, "")
  db_address            = try(aws_db_instance.cerveau[0].address, "")
  db_port               = try(aws_db_instance.cerveau[0].port, var.db_port)
  database_url = (
    var.enable_managed_db && local.db_address != "" ?
    "postgresql+psycopg2://${var.db_username}:${local.db_password_effective}@${local.db_address}:${local.db_port}/${var.db_name}" :
    "sqlite:////tmp/cerveau.db"
  )
  s3_memory_bucket_name_effective = var.enable_s3_memory_archive ? (
    var.s3_memory_bucket_name != "" ? var.s3_memory_bucket_name : "sotipapier-memory-${data.aws_caller_identity.current.account_id}-${var.region}"
  ) : ""
}

resource "random_password" "db_password" {
  count   = var.enable_managed_db && var.db_password == "" ? 1 : 0
  length  = 24
  special = false
}

resource "aws_security_group" "rds" {
  count       = var.enable_managed_db ? 1 : 0
  name        = "sotipapier-rds-access"
  description = "PostgreSQL access from orchestrator instance"
  vpc_id      = data.aws_subnet.orchestrator_primary_subnet.vpc_id

  ingress {
    description     = "PostgreSQL depuis orchestrateur"
    from_port       = var.db_port
    to_port         = var.db_port
    protocol        = "tcp"
    security_groups = data.aws_instance.orchestrator.vpc_security_group_ids
  }

  egress {
    description = "Sortie libre"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "cerveau" {
  count      = var.enable_managed_db ? 1 : 0
  name       = "sotipapier-cerv-db-subnets"
  subnet_ids = data.aws_subnets.orchestrator_vpc_subnets.ids
}

resource "aws_db_instance" "cerveau" {
  count                        = var.enable_managed_db ? 1 : 0
  identifier                   = "sotipapier-cerv-db"
  engine                       = "postgres"
  engine_version               = var.db_engine_version
  instance_class               = var.db_instance_class
  allocated_storage            = var.db_allocated_storage
  db_name                      = var.db_name
  username                     = var.db_username
  password                     = local.db_password_effective
  port                         = var.db_port
  db_subnet_group_name         = aws_db_subnet_group.cerveau[0].name
  vpc_security_group_ids       = [aws_security_group.rds[0].id]
  backup_retention_period      = var.db_backup_retention_days
  publicly_accessible          = var.db_publicly_accessible
  skip_final_snapshot          = var.db_skip_final_snapshot
  deletion_protection          = var.db_deletion_protection
  auto_minor_version_upgrade   = true
  apply_immediately            = true
  performance_insights_enabled = false
  copy_tags_to_snapshot        = true
  storage_encrypted            = true
}

resource "aws_s3_bucket" "memory_archive" {
  count  = var.enable_s3_memory_archive ? 1 : 0
  bucket = local.s3_memory_bucket_name_effective
}

resource "aws_s3_bucket_public_access_block" "memory_archive" {
  count  = var.enable_s3_memory_archive ? 1 : 0
  bucket = aws_s3_bucket.memory_archive[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "memory_archive" {
  count  = var.enable_s3_memory_archive ? 1 : 0
  bucket = aws_s3_bucket.memory_archive[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "null_resource" "deploy_cerveau" {
  count = var.deploy_on_apply && var.ssh_private_key_path != "" && var.cerveau_src_dir != "" ? 1 : 0

  triggers = {
    instance_id  = var.orchestrator_instance_id
    project_src  = var.cerveau_src_dir
    source_hash  = local.source_files_hash
    data_src     = local.data_sources_hash
    url_a        = var.url_instance_a
    url_mpchimie = var.url_classification_mp_chimie
    url_recette  = var.url_recette_agent
    ollama_url   = var.ollama_base_url
    ollama_model = var.ollama_model
    inventory_xl = var.inventory_excel_path
    port         = tostring(var.orchestrator_port)
    cors         = var.cors_origins
    database_url = local.database_url
    auth_exp     = tostring(var.auth_access_token_expire_minutes)
    auth_secret  = var.auth_secret_key
    auth_google  = var.auth_google_client_ids
    auth_admin_bootstrap = var.auth_admin_bootstrap_key
    auth_admin_emails    = var.auth_admin_emails
    erp_timeout          = tostring(var.erp_sql_connect_timeout_seconds)
    self_learning_path   = var.self_learning_db_long_memory_path
    s3_bucket    = local.s3_memory_bucket_name_effective
    s3_sqlite_key = var.s3_sqlite_key
    s3_sqlite_snapshot_prefix = var.s3_sqlite_snapshot_prefix
    s3_sqlite_sync_interval_seconds = tostring(var.s3_sqlite_sync_interval_seconds)
  }

  connection {
    type        = "ssh"
    host        = local.public_ip
    user        = var.ssh_user
    private_key = file(var.ssh_private_key_path)
    timeout     = "20m"
  }

  provisioner "remote-exec" {
    inline = [
      # Supprime le data_sources vide créé par Docker (root) si le déploiement précédent n’avait pas de fichiers.
      "bash -lc 'sudo rm -rf ${var.remote_deploy_dir}/data_sources; mkdir -p ${var.remote_deploy_dir} && sudo chown -R ${var.ssh_user}:${var.ssh_user} ${var.remote_deploy_dir}'",
    ]
  }

  # docker-compose monte ../data_sources → même niveau que cerveau_orchestrateur sur l’EC2.
  # Gros dossiers : scp -r coupe souvent la connexion (broken pipe) ; un flux tar + keepalive SSH est plus fiable.
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      DS="${abspath(local.data_sources_src)}"
      KEY="${replace(var.ssh_private_key_path, "\"", "")}"
      HOST="${local.public_ip}"
      USER="${var.ssh_user}"
      REMOTE="${replace(var.remote_deploy_dir, "\"", "")}"
      if [[ -d "$DS" ]]; then
        DS_PARENT="$(dirname "$DS")"
        DS_NAME="$(basename "$DS")"
        ( cd "$DS_PARENT" && tar czf - "$DS_NAME" ) | ssh \
          -i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
          -o ServerAliveInterval=30 -o ServerAliveCountMax=240 -o TCPKeepAlive=yes -o ConnectTimeout=30 \
          "$USER@$HOST" "set -euo pipefail; mkdir -p '$REMOTE' && cd '$REMOTE' && tar xzf -"
        ssh \
          -i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
          -o ServerAliveInterval=30 -o ServerAliveCountMax=240 -o TCPKeepAlive=yes -o ConnectTimeout=30 \
          "$USER@$HOST" "sudo chown -R $USER:$USER '$REMOTE/data_sources'"
      fi
    EOT
  }

  provisioner "file" {
    source      = var.cerveau_src_dir
    destination = var.remote_deploy_dir
  }

  provisioner "remote-exec" {
    inline = [
      <<-EOT
      bash -lc '
        set -euo pipefail
        REMOTE="${var.remote_deploy_dir}"
        if [ ! -f "$REMOTE/docker-compose.yml" ] && [ -f "$REMOTE/${local.cerveau_basename}/docker-compose.yml" ]; then
          REMOTE="$REMOTE/${local.cerveau_basename}"
        fi
        test -f "$REMOTE/docker-compose.yml" || (echo "ERROR: docker-compose.yml introuvable sous ${var.remote_deploy_dir} (ni sous-dossier ${local.cerveau_basename})" && exit 2)
        docker info >/dev/null 2>&1 || (echo "ERROR: Docker non disponible sur l’instance" && exit 2)

        cat > "$REMOTE/.env.deploy" << ENVEOF
URL_INSTANCE_A=${var.url_instance_a}
URL_CLASSIFICATION_MP_CHIMIE=${var.url_classification_mp_chimie}
URL_RECETTE_AGENT=${var.url_recette_agent}
OLLAMA_BASE_URL=${var.ollama_base_url}
OLLAMA_MODEL=${var.ollama_model}
ORCHESTRATOR_PORT=${var.orchestrator_port}
INVENTORY_EXCEL_PATH=${var.inventory_excel_path}
INVENTORY_DASHBOARD_TOP_N=${var.inventory_dashboard_top_n}
INVENTORY_CLASSIFICATION_MAX_ITEMS=${var.inventory_classification_max_items}
INVENTORY_CLASSIFICATION_CONCURRENCY=${var.inventory_classification_concurrency}
DATABASE_URL=${local.database_url}
AUTH_SECRET_KEY=${var.auth_secret_key}
AUTH_ALGORITHM=HS256
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=${var.auth_access_token_expire_minutes}
AUTH_GOOGLE_CLIENT_IDS=${var.auth_google_client_ids}
AUTH_ADMIN_BOOTSTRAP_KEY=${var.auth_admin_bootstrap_key}
AUTH_ADMIN_EMAILS=${var.auth_admin_emails}
ERP_SQL_CONNECT_TIMEOUT_SECONDS=${var.erp_sql_connect_timeout_seconds}
SELF_LEARNING_DB_LONG_MEMORY_PATH=${var.self_learning_db_long_memory_path}
S3_MEMORY_BUCKET=${local.s3_memory_bucket_name_effective}
S3_SQLITE_KEY=${var.s3_sqlite_key}
S3_SQLITE_SNAPSHOT_PREFIX=${var.s3_sqlite_snapshot_prefix}
S3_SQLITE_SYNC_INTERVAL_SECONDS=${var.s3_sqlite_sync_interval_seconds}
LANGSMITH_TRACING=${var.langsmith_tracing}
LANGSMITH_PROJECT=${var.langsmith_project}
LANGSMITH_ENDPOINT=${var.langsmith_endpoint}
LANGSMITH_API_KEY=${var.langsmith_api_key}
CORS_ORIGINS=${var.cors_origins}
ENVEOF

        cd "$REMOTE"
        docker compose --env-file .env.deploy up -d --build
        docker compose --env-file .env.deploy ps
      '
      EOT
    ]
  }
}
