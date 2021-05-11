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

variable "parameters" {
    type        = map
    description = "Paraemters to feed into cloudformation"
}

variable "template_filename" {
    type        = string
    description = "Filename of CloudFormation Template file in asset_dir (usually <stack_name>.template.json)"
}
