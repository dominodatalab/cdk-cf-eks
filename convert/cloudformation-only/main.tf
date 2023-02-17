resource "aws_iam_policy" "cloudformation_only" {
  name = "cloudformation-only"

  policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Action = ["cloudformation:*"]
          Effect = "Allow"
          Resource = "*"
        },
      ]
  })
}

resource "aws_iam_role" "cloudformation_only" {
  name = "cloudformation-only"
  description = "Allows CloudFormation to create and manage AWS stacks and resources on your behalf, but nothing else"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = ""
        Principal = {
          Service = "cloudformation.amazonaws.com"
        }
      },
    ]
  })

  managed_policy_arns = [aws_iam_policy.cloudformation_only.arn]
}

output "cloudformation_only_role" {
  description = "cloudformation-only role"
  value       = aws_iam_role.cloudformation_only.arn
}
