resource "aws_iam_policy" "deployment" {
    count = var.iam_policy_path != "" ? 1: 0

    name = "${var.name}-deployment-policy"

    policy = file(var.iam_policy_path)

    tags = var.tags
}

resource "aws_iam_role" "deployment" {
    count = var.iam_policy_path != "" ? 1: 0

    name = "${var.name}-deployment-role"

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

    managed_policy_arns = [
        aws_iam_policy.deployment[0].arn
    ]

    provisioner "local-exec" {
      command = "sleep 15"
    }

    tags = var.tags
}
