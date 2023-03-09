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

variable "flow_logging" {
  type        = bool
  description = "Enable flow logging"
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

variable "default_node_groups" {
  type        = map
  description = "Default node groups"
}

variable "additional_node_groups" {
  type        = map
  description = "Additional EKS managed nodegroups"
  default     = {}
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
  description = "Custom role maps for aws auth configmap"
  default     = []
}

variable "eks_cluster_auto_sg" {
  description = "Atomatically generated security group with name in the form of eks-cluster-sg-<clustername>"
  type        = string
}

variable "s3_force_destroy_on_deletion" {
  type        = bool
  description = "Toogle to allow recursive deletion of all objects in the s3 buckets. if 'false' terraform will NOT be able to delete non-empty buckets"
  default     = false
}

variable "use_kms" {
  type        = bool
  description = "If set, use either the specified KMS key or a Domino-generated one"
  default     = false
}

variable "kms_key_id" {
  type        = string
  description = "If use_kms is set, use the specified KMS key"
  default     = null
}

variable "ecr_force_destroy_on_deletion" {
  type        = bool
  description = "Toogle to allow recursive deletion of all objects in the ECR repositories. if 'false' terraform will NOT be able to delete non-empty repositories"
  default     = false
}

variable "kubeconfig_path" {
  type        = string
  description = "fully qualified path name to write the kubeconfig file"
  default     = ""
}

variable "flow_log_bucket_arn" {
  type        = string
  description = ""
  default     = ""
}
