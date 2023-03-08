module "domino_eks" {
  source                        = "github.com/dominodatalab/terraform-aws-eks.git?ref=v1.3.0"
  deploy_id                     = var.deploy_id
  region                        = var.region
  tags                          = var.tags
  k8s_version                   = var.k8s_version
  default_node_groups           = var.default_node_groups
  route53_hosted_zone_name      = var.route53_hosted_zone_name
# cidr
  bastion                       = {}
  s3_force_destroy_on_deletion  = var.s3_force_destroy_on_deletion
  ssh_pvt_key_path              = var.ssh_key_path
  kubeconfig_path               = var.kubeconfig_path
  use_kms                       = var.use_kms
  kms_key_id                    = var.kms_key_id
  ecr_force_destroy_on_deletion = var.ecr_force_destroy_on_deletion
  eks_master_role_names         = var.eks_master_role_names
  vpc_id                        = var.vpc_id
  public_subnets                = var.public_subnet_ids
  private_subnets               = var.private_subnet_ids
  pod_subnets                   = var.pod_subnet_ids
  update_kubeconfig_extra_args  = "--role-arn ${aws_iam_role.grandfathered_creation_role.arn}"
  eks_custom_role_maps          = var.eks_custom_role_maps
}
