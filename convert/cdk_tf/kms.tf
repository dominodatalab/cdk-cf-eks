resource "aws_kms_key" "eks_cluster" {
  description              = "KMS key to secure data for Domino"
  customer_master_key_spec = "SYMMETRIC_DEFAULT"
  enable_key_rotation      = true
  is_enabled               = true
  key_usage                = "ENCRYPT_DECRYPT"
  multi_region             = false
}
