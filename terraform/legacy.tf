output "BASTION_IP" {
  value = aws_cloudformation_stack.cdk_stack.outputs.bastionpublicip
}

output "S3_BUCKET_NAME" {
  value = aws_cloudformation_stack.cdk_stack.outputs.blobsbucketoutput
}

output "S3_LOG_SNAPS_BUCKET_NAME" {
  value = aws_cloudformation_stack.cdk_stack.outputs.logsbucketoutput
}

output "S3_BACKUPS_BUCKET_NAME" {
  value = aws_cloudformation_stack.cdk_stack.outputs.backupsbucketoutput
}

output "S3_REGISTRY_BUCKET_NAME" {
  value = aws_cloudformation_stack.cdk_stack.outputs.registrybucketoutput
}

output "S3_MONITORING_BUCKET_NAME" {
  value = aws_cloudformation_stack.cdk_stack.outputs.monitoringbucketoutput
}

output "EXECUTOR_EFS_FS_ID" {
  value = aws_cloudformation_stack.cdk_stack.outputs.EFSFilesystemId
}

output "EXECUTOR_EFS_AP_ID" {
  value = aws_cloudformation_stack.cdk_stack.outputs.EFSAccessPointId
}
