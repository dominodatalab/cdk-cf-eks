resource "aws_cloudformation_stack" "cdk_stack" {
  name = var.name
  capabilities = [
    "CAPABILITY_IAM",
    "CAPABILITY_NAMED_IAM"
  ]
  parameters = var.parameters
  template_url = "https://${aws_s3_bucket.cf_asset_bucket.bucket_regional_domain_name}/${var.template_filename}"
  iam_role_arn = var.iam_role_arn
  depends_on = [aws_s3_bucket_object.assets]
  timeout_in_minutes = var.cloudformation_timeout_in_minutes

  timeouts {
    create = "${var.cloudformation_timeout_in_minutes}m"
    update = "${var.cloudformation_timeout_in_minutes}m"
    delete = "${var.cloudformation_timeout_in_minutes}m"
  }
}

output "cloudformation_outputs" {
  value = aws_cloudformation_stack.cdk_stack.outputs
}

resource "local_file" "agent_template" {
  content = lookup(aws_cloudformation_stack.cdk_stack.outputs, "agentconfig", "")
  filename = abspath("${var.output_dir}/agent_template.yaml")
  file_permission = "0600"
  depends_on = [aws_cloudformation_stack.cdk_stack]
}

resource "null_resource" "kubeconfig" {
  provisioner "local-exec" {
    command = "${lookup(aws_cloudformation_stack.cdk_stack.outputs, "ekskubeconfigcmd", "")} --kubeconfig ${abspath("${var.output_dir}/kubeconfig")}"
  }

  depends_on = [aws_cloudformation_stack.cdk_stack]
}
