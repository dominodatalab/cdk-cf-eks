module "eks" {
  source                        = "github.com/dominodatalab/terraform-aws-eks.git?ref=v1.3.0"
  deploy_id                     = var.deploy_id
  region                        = var.region
  tags                          = var.tags
  k8s_version                   = var.k8s_version
  default_node_groups           = var.default_node_groups
  route53_hosted_zone_name      = var.route53_hosted_zone_name
# cidr
  bastion                       = {}
  s3_force_destroy_on_deletion  = var.s3_force_destroy_on_deletion
  ssh_pvt_key_path              = var.ssh_key_path
  kubeconfig_path               = var.kubeconfig_path
  use_kms                       = var.use_kms
  kms_key_id                    = var.kms_key_id
  ecr_force_destroy_on_deletion = var.ecr_force_destroy_on_deletion
  eks_master_role_names         = var.eks_master_role_names
  vpc_id                        = var.vpc_id
  public_subnets                = var.public_subnet_ids
  private_subnets               = var.private_subnet_ids
  pod_subnets                   = var.pod_subnet_ids
  update_kubeconfig_extra_args  = "--role-arn ${aws_iam_role.grandfathered_creation_role.arn}"
  eks_custom_role_maps          = var.eks_custom_role_maps
}

output "KEY_PAIR_NAME" {
  description = "Name of Provisioned AWS Keypair"
  value       = module.eks.domino_key_pair.key_name
}

output "S3_BUCKET_NAME" {
  description = "Blobs bucket name"
  value       = module.eks.s3_buckets.blobs.bucket_name
}

output "S3_LOG_SNAPS_BUCKET_NAME" {
  description = "Log bucket name"
  value       = module.eks.s3_buckets.logs.bucket_name
}

output "S3_BACKUPS_BUCKET_NAME" {
  description = "Backup bucket name"
  value       = module.eks.s3_buckets.backups.bucket_name
}

output "S3_REGISTRY_BUCKET_NAME" {
  description = "Docker Registry bucket name"
  value       = module.eks.s3_buckets.registry.bucket_name
}

output "S3_MONITORING_BUCKET_NAME" {
  description = "Monitoring bucket name"
  value       = module.eks.s3_buckets.monitoring.bucket_name
}

output "EXECUTOR_EFS_FS_ID" {
  description = "EFS filesystem ID"
  value       = module.eks.efs_file_system.id
}

output "EXECUTOR_EFS_AP_ID" {
  description = "EFS access point ID"
  value       = module.eks.efs_access_point.id
}

output "BASTION_IP" {
  description = "Bastion instance IP address"
  value       = module.eks.bastion_ip
}

output "KMS_KEY_ID" {
  description = "KMS key ID, if enabled"
  value       = module.eks.kms_key_id
}
