variable "deploy_id" {
  type        = string
  description = "Domino Deployment ID."
}


variable "region" {
  type        = string
  description = "AWS region for the deployment"
}


variable "grandfathered_creation_role" {
  type        = string
  description = "Role CDK used to create EKS"
}


variable "tags" {
  type        = map(string)
  description = "Deployment tags."
}

variable "vpc_id" {
  type        = string
  description = "Pre-existing VPC ID for deployment"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Pre-existing public subnets ids used with deployment"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Pre-existing private subnets ids used with deployment"
}

variable "pod_subnet_ids" {
  type        = list(string)
  description = "Pre-existing private subnets ids used with deployment"
}

variable "k8s_version" {
  type        = string
  description = "EKS cluster k8s version (should match existing)"
}

variable "ssh_key_path" {
  type        = string
  description = "Path to private SSH key"
}

variable "number_of_azs" {
  type        = number
  description = "Number of AZs used in deployment (usually 3)"
  default     = 3
}

variable "route53_hosted_zone_name" {
  type        = string
  description = "Name of route53 hosted zone (optional, for internal use)"
  default     = ""
}

variable "efs_backups" {
  type        = bool
  description = "Enable EFS backups"
}

variable "efs_backup_schedule" {
  type        = string
  description = "Cron-style schedule for EFS backup vault"
  default     = "0 12 * * ? *"
}

variable "efs_backup_cold_storage_after" {
  type        = number
  description = "Move backup data to cold storage after this many days"
  default     = 35
}

variable "efs_backup_delete_after" {
  type        = number
  description = "Delete backup data after this many days"
  default     = 125
}

variable "efs_backup_force_destroy" {
  type        = bool
  description = "Destroy all backup points when destroying backup vault"
  default     = false
}

variable "eks_master_role_names" {
  type        = list(string)
  description = "Extra roles for EKS master IAM role for monitoring, etc. (optional)"
  default     = []
}

variable "eks_custom_role_maps" {
  type        = list(object({rolearn = string, username = string, groups = list(string)}))
  description = "blah"
  default     = []
}