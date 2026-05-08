output "orchestrator_instance_id" {
  value       = data.aws_instance.orchestrator.id
  description = "ID de l’instance EC2 cible du cerveau orchestrateur."
}

output "orchestrator_public_ip" {
  value       = data.aws_instance.orchestrator.public_ip
  description = "IP publique de l’instance (accès SSH / HTTP)."
}

output "orchestrator_private_ip" {
  value       = data.aws_instance.orchestrator.private_ip
  description = "IP privée de l’instance orchestrateur (usage intra-VPC)."
}

output "orchestrator_public_dns" {
  value       = data.aws_instance.orchestrator.public_dns
  description = "DNS public de l’instance (si présent)."
}

output "orchestrator_api_url" {
  value       = data.aws_instance.orchestrator.public_ip != "" ? "http://${data.aws_instance.orchestrator.public_ip}:${var.orchestrator_port}" : "http://${data.aws_instance.orchestrator.private_ip}:${var.orchestrator_port}"
  description = "URL de base de l’API orchestrateur (FastAPI)."
}

output "ask_agent_endpoint" {
  value       = data.aws_instance.orchestrator.public_ip != "" ? "http://${data.aws_instance.orchestrator.public_ip}:${var.orchestrator_port}/api/v1/ask_agent" : "http://${data.aws_instance.orchestrator.private_ip}:${var.orchestrator_port}/api/v1/ask_agent"
  description = "Endpoint POST pour l’agent."
}

output "aws_account_id" {
  value       = data.aws_caller_identity.current.account_id
  description = "Compte AWS utilisé par Terraform."
}

output "ssh_command" {
  value       = "ssh -i <YOUR_PEM> ${var.ssh_user}@${data.aws_instance.orchestrator.public_ip}"
  description = "Modèle de commande SSH."
}

output "remote_deploy_dir" {
  value       = var.remote_deploy_dir
  description = "Chemin de déploiement distant du cerveau orchestrateur."
}

output "database_url_runtime" {
  value       = local.database_url
  description = "DATABASE_URL injectée dans le backend."
  sensitive   = true
}

output "rds_endpoint" {
  value       = try(aws_db_instance.cerveau[0].address, "")
  description = "Endpoint RDS PostgreSQL (si activé)."
}

output "rds_port" {
  value       = try(aws_db_instance.cerveau[0].port, 0)
  description = "Port RDS PostgreSQL (si activé)."
}

output "rds_master_password" {
  value       = local.db_password_effective
  description = "Mot de passe PostgreSQL effectif."
  sensitive   = true
}

output "s3_memory_bucket" {
  value       = try(aws_s3_bucket.memory_archive[0].bucket, "")
  description = "Bucket S3 archive mémoire (si activé)."
}
