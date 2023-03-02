variable "region" {
  type        = string
  description = "AWS region for the deployment"
}

variable "tags" {
  type        = map(string)
  description = "Deployment tags."
}

variable "suffix" {
  type        = string
  description = "Optional suffix for role/policy names"
  default     = ""
}
