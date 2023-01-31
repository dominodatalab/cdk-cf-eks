resource "aws_cloudformation_stack" "cdk_stack" {
  name = var.name
  capabilities = [
    "CAPABILITY_IAM",
    "CAPABILITY_NAMED_IAM"
  ]
  parameters         = var.parameters
  template_url       = "https://${aws_s3_bucket.cf_asset_bucket.bucket_regional_domain_name}/${var.template_filename}"
  iam_role_arn       = length(var.iam_policy_paths) != 0 ? aws_iam_role.deployment[0].arn : var.iam_role_arn
  depends_on         = [aws_s3_bucket_object.assets]
  timeout_in_minutes = var.cloudformation_timeout_in_minutes
  disable_rollback = var.disable_rollback

  timeouts {
    create = "${var.cloudformation_timeout_in_minutes}m"
    update = "${var.cloudformation_timeout_in_minutes}m"
    delete = "${var.cloudformation_timeout_in_minutes}m"
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [disable_rollback]
  }
}

output "cloudformation_outputs" {
  value = aws_cloudformation_stack.cdk_stack.outputs
}

resource "null_resource" "kubeconfig" {
  provisioner "local-exec" {
    command = "${lookup(aws_cloudformation_stack.cdk_stack.outputs, "ekskubeconfigcmd", "")} --kubeconfig ${abspath("${var.output_dir}/kubeconfig")} && chmod 600 ${abspath("${var.output_dir}/kubeconfig")}"
  }

  depends_on = [aws_cloudformation_stack.cdk_stack]
}
