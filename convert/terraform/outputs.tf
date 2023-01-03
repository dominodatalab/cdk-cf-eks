output "domino_eks" {
  description = "EKS module outputs"
  value       = module.domino_eks
}

output "KEY_PAIR_NAME" {
  description = "Name of Provisioned AWS Keypair"
  value       = module.domino_eks.domino_key_pair.key_name
}

output "S3_BUCKET_NAME" {
  description = "Blobs bucket name"
  value       = module.domino_eks.s3_buckets.blobs.bucket_name
}

output "S3_LOG_SNAPS_BUCKET_NAME" {
  description = "Log bucket name"
  value       = module.domino_eks.s3_buckets.logs.bucket_name
}

output "S3_BACKUPS_BUCKET_NAME" {
  description = "Backup bucket name"
  value       = module.domino_eks.s3_buckets.backups.bucket_name
}

output "S3_REGISTRY_BUCKET_NAME" {
  description = "Docker Registry bucket name"
  value       = module.domino_eks.s3_buckets.registry.bucket_name
}

output "S3_MONITORING_BUCKET_NAME" {
  description = "Monitoring bucket name"
  value       = module.domino_eks.s3_buckets.monitoring.bucket_name
}

output "EXECUTOR_EFS_FS_ID" {
  description = "EFS filesystem ID"
  value       = module.domino_eks.efs_file_system.id
}

output "EXECUTOR_EFS_AP_ID" {
  description = "EFS access point ID"
  value       = module.domino_eks.efs_access_point.id
}

output "BASTION_IP" {
  description = "Bastion instance IP address"
  value       = module.domino_eks.bastion_ip
}
