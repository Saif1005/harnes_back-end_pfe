output "public_ip" {
  value       = var.existing_instance_id != "" ? data.aws_instance.existing[0].public_ip : aws_instance.agi[0].public_ip
  description = "Public IP of the EC2 instance"
}

output "private_ip" {
  value       = var.existing_instance_id != "" ? data.aws_instance.existing[0].private_ip : aws_instance.agi[0].private_ip
  description = "Private IPv4 (VPC) — à utiliser dans url_instance_a depuis une autre EC2 du même VPC (ex. cerveau orchestrateur)"
}

output "aws_account_id" {
  value       = data.aws_caller_identity.current.account_id
  description = "AWS account id used by Terraform provider"
}

output "aws_arn" {
  value       = data.aws_caller_identity.current.arn
  description = "Caller ARN used by Terraform provider"
}

output "ssh_command" {
  value       = "ssh -i <YOUR_PEM> ${var.ssh_user}@${var.existing_instance_id != "" ? data.aws_instance.existing[0].public_ip : aws_instance.agi[0].public_ip}"
  description = "SSH command template"
}

output "tool_endpoints" {
  description = "URLs publiques des APIs Docker (remplacer l’IP si Elastic IP différente)"
  value = {
    agent_pdr_mp_pdr               = "http://${var.existing_instance_id != "" ? data.aws_instance.existing[0].public_ip : aws_instance.agi[0].public_ip}:8000"
    agent_classification_mp_chimie = "http://${var.existing_instance_id != "" ? data.aws_instance.existing[0].public_ip : aws_instance.agi[0].public_ip}:8001"
    agent_recette                  = "http://${var.existing_instance_id != "" ? data.aws_instance.existing[0].public_ip : aws_instance.agi[0].public_ip}:8002"
  }
}

output "tool_endpoints_private_vpc" {
  description = "URLs avec IP privée — joignables depuis une autre instance du même VPC (ex. terraform_cerveau url_instance_a)"
  value = {
    agent_pdr_mp_pdr               = "http://${var.existing_instance_id != "" ? data.aws_instance.existing[0].private_ip : aws_instance.agi[0].private_ip}:8000/api/v1/classify"
    agent_classification_mp_chimie = "http://${var.existing_instance_id != "" ? data.aws_instance.existing[0].private_ip : aws_instance.agi[0].private_ip}:8001/api/v1/classify"
    agent_recette                  = "http://${var.existing_instance_id != "" ? data.aws_instance.existing[0].private_ip : aws_instance.agi[0].private_ip}:8002/api/v1/recette"
  }
}

