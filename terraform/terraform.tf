provider "aws" {
  version = "~> 3.37.0"
  region  = var.aws_region
}

terraform {
  required_version = ">= 0.12"
}
