variable "asset_bucket" {
  type        = string
  description = "Bucket to create and deploy CDK assets to"
}

variable "asset_dir" {
  type        = string
  description = "Local path of CDK asset directory"
}

variable "aws_region" {
  type        = string
  description = "AWS Region to deploy stack into"
}

variable "name" {
  type        = string
  description = "Unique identifier for deployment"
}

variable "output_dir" {
  type        = string
  description = "Output directory for agent_template.yaml and kubeconfig"
}

variable "parameters" {
  type        = map
  description = "Parameters to feed into cloudformation"
}

variable "template_filename" {
  type        = string
  description = "Filename of CloudFormation Template file in asset_dir (usually <stack_name>.template.json)"
}

variable "iam_role_arn" {
  type        = string
  description = "Pre-existing IAM role to use for deployment"
  default     = ""
}

variable "iam_policy_path" {
  type        = string
  description = "IAM policy to provision and use for deployment"
  default     = ""
}

variable "cloudformation_timeout_in_minutes" {
  type        = number
  description = "CloudFormation provisioning timeout in minutes"
  default     = 60
}

variable "tags" {
  type        = map
  description = "Tags to apply to all resources (not including what CloudFormation provisions)"
  default     = {}
}
