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
