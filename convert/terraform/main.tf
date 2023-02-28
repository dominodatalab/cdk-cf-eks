data "aws_caller_identity" "admin" {}
data "aws_partition" "current" {}

resource "aws_iam_role" "grandfathered_creation_role" {
  name = var.grandfathered_creation_role

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = ""
        Principal = {
          AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.admin.account_id}:root"
        }
      },
    ]
  })

  lifecycle {
    ignore_changes = [name, inline_policy]
  }
}

module "domino_eks" {
  source                       = "github.com/dominodatalab/terraform-aws-eks.git?ref=main"
  deploy_id                    = var.deploy_id
  region                       = var.region
  default_node_groups          = var.default_node_groups
  k8s_version                  = var.k8s_version
  route53_hosted_zone_name     = var.route53_hosted_zone_name
  eks_master_role_names        = var.eks_master_role_names
  s3_force_destroy_on_deletion = var.s3_force_destroy_on_deletion
  bastion                      = {}
  ssh_pvt_key_path             = var.ssh_key_path
  tags                         = var.tags
  vpc_id                       = var.vpc_id
  public_subnets               = var.public_subnet_ids
  private_subnets              = var.private_subnet_ids
  pod_subnets                  = var.pod_subnet_ids
  update_kubeconfig_extra_args = "--role-arn ${aws_iam_role.grandfathered_creation_role.arn}"
  eks_custom_role_maps         = var.eks_custom_role_maps
}
