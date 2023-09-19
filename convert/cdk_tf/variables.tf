
variable "tags" {
  type        = map(string)
  description = "Deployment tags."
}

variable "deploy_id" {
  type        = string
  description = "Domino Deployment ID."
}

variable "region" {
  type        = string
  description = "AWS region for the deployment"
}

variable "flow_logging" {
  type        = bool
  description = "Enable flow logging"
}

variable "eks_cluster_auto_sg" {
  description = "Atomatically generated security group with name in the form of eks-cluster-sg-<clustername>"
  type        = string
}

variable "number_of_azs" {
  type        = number
  description = "Number of AZs used in deployment (usually 3)"
  default     = 3
}

variable "flow_log_bucket_arn" {
  type        = string
  description = "Bucket for vpc flow logging"
  default     = ""
}
