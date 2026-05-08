variable "region" {
  type        = string
  description = "AWS region"
  default     = "eu-west-3"
}

variable "aws_profile" {
  type        = string
  description = "AWS shared config/credentials profile name to use (leave empty to use default env credentials)"
  default     = ""
}

variable "name" {
  type        = string
  description = "Name prefix for resources"
  default     = "projet-industriel-agi"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type (GPU recommended: g4dn.xlarge)"
  default     = "g4dn.xlarge"
}

variable "ami_id" {
  type        = string
  description = "AMI ID to use (leave empty to use Ubuntu 20.04 Canonical lookup)"
  default     = ""
}

variable "existing_instance_id" {
  type        = string
  description = "If set, Terraform will NOT create an instance and will target this existing EC2 instance for deployment."
  default     = ""
}

variable "key_name" {
  type        = string
  description = "EC2 Key Pair name (must already exist in the region)"
}

variable "ssh_private_key_path" {
  type        = string
  description = "Local path to the PEM private key (used for optional SSH provisioners)"
  default     = ""
}

variable "ssh_user" {
  type        = string
  description = "SSH user for the AMI"
  default     = "ubuntu"
}

variable "allowed_ssh_cidr" {
  type        = string
  description = "CIDR allowed to SSH into the instance (recommend your public IP /32)"
  default     = "0.0.0.0/0"
}

variable "open_ports_cidrs" {
  type        = list(string)
  description = "CIDRs autorisés vers les APIs Docker hébergées sur l’instance : 8000 (agent-pdr), 8001 (agent-classification), 8002 (agent_recette). Restreindre en prod (/32)."
  default     = ["0.0.0.0/0"]
}

variable "manage_existing_instance_sg_ingress" {
  type        = bool
  description = "Si true et existing_instance_id est renseigné, Terraform crée les règles TCP 8000/8001/8002. Mettre false si ces ports sont déjà ouverts dans le SG (sinon erreur InvalidPermission.Duplicate)."
  default     = false
}

variable "project_src_dir" {
  type        = string
  description = "Local path to the folder projet_industriel_agi/ (used for optional copy)"
  default     = ""
}

variable "remote_deploy_dir" {
  type        = string
  description = "Remote path on the instance where the project will be copied"
  default     = "/home/ubuntu/projet_industriel_agi"
}

variable "ssh_connection_timeout" {
  type        = string
  description = "Timeout connexion SSH pour les provisioners (upload lourd : 45m–60m recommandé)"
  default     = "45m"
}

variable "deploy_use_rsync" {
  type        = bool
  description = "true = copie avec rsync (rapide, exclusions, reprise partielle). false = provisioner file Terraform (SCP interne, tout le dossier)."
  default     = true
}

variable "deploy_rsync_excludes" {
  type        = list(string)
  description = "Motifs rsync --exclude (chemins relatifs à project_src_dir). Par défaut : gros artefacts non nécessaires au code."
  default = [
    ".git/",
    "local_models/",
    ".terraform/",
    "__pycache__/",
    ".cursor/",
    "*.pyc",
    "agent_pdr_microservice/models_saved/xlm_roberta_large_mp_chimie/",
  ]
}

variable "deploy_train_agent_pdr" {
  type        = bool
  description = "If true, runs the one-shot training container agent-pdr-train during terraform deploy"
  default     = true
}

variable "deploy_train_agent_pdr_async" {
  type        = bool
  description = "If true, starts agent-pdr-train in background so terraform apply does not wait for training completion"
  default     = true
}

variable "deploy_start_agent_pdr" {
  type        = bool
  description = "If true, starts the agent-pdr API container during terraform deploy (port 8000)"
  default     = true
}

variable "deploy_start_agent_classification" {
  type        = bool
  description = "If true, starts agent-classification (MP/CHIMIE, port 8001) after deploy"
  default     = true
}

variable "deploy_start_agent_recette" {
  type        = bool
  description = "If true, starts agent_recette (port 8002 → conteneur 8001)"
  default     = true
}

