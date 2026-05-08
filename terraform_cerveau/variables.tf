variable "region" {
  type        = string
  description = "Région AWS (doit correspondre à l’instance EC2)."
  default     = "eu-west-3"
}

variable "aws_profile" {
  type        = string
  description = "Profil AWS CLI (vide = défaut / variables d’environnement)."
  default     = ""
}

variable "orchestrator_instance_id" {
  type        = string
  description = "ID de l’instance EC2 où tourne le cerveau orchestrateur (Instance B, distincte de l’instance PDR/GPU)."
  default     = "i-0cda9e47365df591b"
}

variable "ssh_private_key_path" {
  type        = string
  description = "Chemin local vers la clé PEM pour SSH (provisioner Terraform)."
}

variable "ssh_user" {
  type        = string
  description = "Utilisateur SSH sur l’AMI (souvent ubuntu)."
  default     = "ubuntu"
}

variable "cerveau_src_dir" {
  type        = string
  description = "Chemin local absolu vers le dossier cerveau_orchestrateur/ (contient Dockerfile et docker-compose.yml)."
}

variable "data_sources_src_dir" {
  type        = string
  description = "Chemin local absolu vers data_sources/ (Excel, CSV pour le volume Docker). Vide = dossier data_sources à côté du parent de cerveau_src_dir (ex. projet_industriel_agi/data_sources)."
  default     = ""
}

variable "remote_deploy_dir" {
  type        = string
  description = "Répertoire distant sur l’instance où le projet est copié."
  default     = "/home/ubuntu/cerveau_orchestrateur"
}

variable "orchestrator_port" {
  type        = number
  description = "Port exposé sur l’hôte pour l’API FastAPI du cerveau."
  default     = 8010
}

variable "url_instance_a" {
  type        = string
  description = "URL complète de l’API classification PDR sur l’autre instance (Instance A), ex. http://IP_PUBLIC:8000/api/v1/classify"

  validation {
    condition     = length(regexall("IP_INSTANCE_PDR", var.url_instance_a)) == 0
    error_message = "Remplacez IP_INSTANCE_PDR dans terraform.tfvars par l’IP ou le DNS joignable depuis l’instance orchestrateur (ex. http://172.31.x.x:8000/api/v1/classify en VPC privé)."
  }
}

variable "url_classification_mp_chimie" {
  type        = string
  description = "URL complète de l’API MP/CHIMIE (agent-classification), ex. http://172.31.x.x:8001/api/v1/classify"
  default     = "http://127.0.0.1:8001/api/v1/classify"
}

variable "url_recette_agent" {
  type        = string
  description = "URL complète du microservice Agent Recette (POST /api/v1/recette), joignable depuis l’instance orchestrateur (ex. http://172.31.x.x:8002/api/v1/recette ou http://127.0.0.1:8002/api/v1/recette si recette sur la même machine en host network)."
  default     = "http://127.0.0.1:8002/api/v1/recette"
}

variable "ollama_base_url" {
  type        = string
  description = "URL Ollama vue depuis le conteneur. Avec docker-compose en network_mode:host : http://127.0.0.1:11434. Sinon Ollama sur l’hôte : OLLAMA_HOST=0.0.0.0:11434 + http://host.docker.internal:11434."
  default     = "http://127.0.0.1:11434"
}

variable "ollama_model" {
  type        = string
  description = "Nom du modèle Ollama (ex. mistral:7b-instruct)."
  default     = "mistral:7b-instruct"
}

variable "cors_origins" {
  type        = string
  description = "Origines CORS autorisées (CSV) pour le frontend qui appelle l’API sur EC2. Ex. http://localhost:5173,https://app.example.com"
  default     = "http://localhost:5173,http://127.0.0.1:5173"
}

variable "inventory_excel_path" {
  type        = string
  description = "Chemin du fichier Excel stock, vu depuis le conteneur orchestrateur."
  default     = "/app/data_sources/piece_de_rechange_data/ECA_PDR_31122023_Raw(AutoRecovered).csv.xlsx"
}

variable "inventory_dashboard_top_n" {
  type        = number
  description = "Nombre d’articles affichés dans le top du dashboard stock."
  default     = 20
}

variable "inventory_classification_max_items" {
  type        = number
  description = "Nombre max d’articles traités par la chaîne de double classification."
  default     = 500
}

variable "inventory_classification_concurrency" {
  type        = number
  description = "Concurrence des appels API classification pendant la construction de la base stock."
  default     = 20
}

variable "langsmith_tracing" {
  type        = bool
  description = "Active les traces LangSmith."
  default     = true
}

variable "langsmith_project" {
  type        = string
  description = "Nom du projet LangSmith."
  default     = "sotipapier-production"
}

variable "langsmith_endpoint" {
  type        = string
  description = "Endpoint LangSmith (US: https://api.smith.langchain.com, EU: https://eu.api.smith.langchain.com)."
  default     = "https://api.smith.langchain.com"
}

variable "langsmith_api_key" {
  type        = string
  description = "Clé API LangSmith (optionnel mais recommandé pour monitoring)."
  default     = ""
  sensitive   = true
}

variable "manage_security_group_rules" {
  type        = bool
  description = "Si true, ajoute une règle ingress TCP sur orchestrator_port sur chaque security group attaché à l’instance."
  default     = true
}

variable "open_ports_cidrs" {
  type        = list(string)
  description = "CIDRs autorisés vers le port du cerveau (8010). Restreindre en production."
  default     = ["0.0.0.0/0"]
}

variable "deploy_on_apply" {
  type        = bool
  description = "Si true, copie le code et exécute docker compose up --build sur l’instance."
  default     = true
}

variable "enable_managed_db" {
  type        = bool
  description = "Si true, crée une base RDS PostgreSQL pour l’auth/mémoire."
  default     = true
}

variable "db_name" {
  type        = string
  description = "Nom logique de la base applicative."
  default     = "sotipapier"
}

variable "db_username" {
  type        = string
  description = "Nom utilisateur master PostgreSQL."
  default     = "sotipapier_admin"
}

variable "db_password" {
  type        = string
  description = "Mot de passe PostgreSQL. Vide = génération Terraform (random_password)."
  default     = ""
  sensitive   = true
}

variable "db_allocated_storage" {
  type        = number
  description = "Taille stockage RDS (GiB)."
  default     = 20
}

variable "db_instance_class" {
  type        = string
  description = "Classe d’instance RDS."
  default     = "db.t3.micro"
}

variable "db_engine_version" {
  type        = string
  description = "Version moteur PostgreSQL."
  default     = "16.3"
}

variable "db_port" {
  type        = number
  description = "Port PostgreSQL."
  default     = 5432
}

variable "db_publicly_accessible" {
  type        = bool
  description = "RDS publique ou privée (recommandé false)."
  default     = false
}

variable "db_backup_retention_days" {
  type        = number
  description = "Durée de rétention backup RDS."
  default     = 7
}

variable "db_deletion_protection" {
  type        = bool
  description = "Protection suppression RDS."
  default     = false
}

variable "db_skip_final_snapshot" {
  type        = bool
  description = "Skip snapshot finale à la suppression (dev)."
  default     = true
}

variable "enable_s3_memory_archive" {
  type        = bool
  description = "Si true, crée un bucket S3 d’archive mémoire long terme / backups."
  default     = true
}

variable "s3_memory_bucket_name" {
  type        = string
  description = "Nom bucket S3 (vide = auto-généré unique)."
  default     = ""
}

variable "auth_secret_key" {
  type        = string
  description = "Secret JWT backend."
  default     = "CHANGE_ME_SECRET_KEY_SOTIPAPIER"
  sensitive   = true
}

variable "auth_access_token_expire_minutes" {
  type        = number
  description = "Durée de vie token JWT (minutes)."
  default     = 480
}

variable "auth_google_client_ids" {
  type        = string
  description = "Liste CSV des Google OAuth Client IDs autorisés pour /auth/google."
  default     = ""
}

variable "auth_admin_bootstrap_key" {
  type        = string
  description = "Clé secrète temporaire pour promouvoir un utilisateur en admin via /auth/admin/bootstrap."
  default     = ""
  sensitive   = true
}

variable "auth_admin_emails" {
  type        = string
  description = "Liste CSV des emails qui doivent toujours avoir le role admin."
  default     = ""
}

variable "erp_sql_connect_timeout_seconds" {
  type        = number
  description = "Timeout (secondes) pour le test de connexion SQL ERP."
  default     = 5
}

variable "self_learning_db_long_memory_path" {
  type        = string
  description = "Chemin local du dossier db_long_memory pour le self-learning."
  default     = "/tmp/db_long_memory"
}

variable "s3_sqlite_key" {
  type        = string
  description = "Clé S3 principale pour la base SQLite runtime."
  default     = "runtime/cerveau.db"
}

variable "s3_sqlite_snapshot_prefix" {
  type        = string
  description = "Préfixe S3 pour snapshots versionnés SQLite."
  default     = "runtime/snapshots"
}

variable "s3_sqlite_sync_interval_seconds" {
  type        = number
  description = "Intervalle de sync SQLite -> S3 (secondes)."
  default     = 180
}
