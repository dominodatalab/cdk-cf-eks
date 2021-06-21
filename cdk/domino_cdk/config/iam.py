
def generate_iam(stack_name: str, aws_account_id: str, terraform: bool = False):
    cloudformation = {
                "Effect": "Allow",
                "Action": [
                    "cloudformation:CreateChangeSet",
                    "cloudformation:DeleteChangeSet",
                    "cloudformation:DeleteStack",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:DescribeStackEvents",
                    "cloudformation:DescribeStacks",
                    "cloudformation:ExecuteChangeSet",
                    "cloudformation:GetTemplate",
                ],
                "Resource": [
                    f"arn:aws:cloudformation:*:{aws_account_id}:stack/{stack_name}-eks-stack/*",
                    f"arn:aws:cloudformation:*:{aws_account_id}:stack/CDKToolkit/*",
                ],
            }

    asset_bucket = {
                "Effect": "Allow",
                "Action": ["s3:*Object", "s3:GetBucketLocation", "s3:ListBucket"],
                "Resource": ["arn:aws:s3:::cdktoolkit-stagingbucket-*"],
            }

    s3 = {
                "Effect": "Allow",
                "Action": [
                    "s3:CreateBucket",
                    "s3:DeleteBucket",
                    "s3:DeleteBucketPolicy",
                    "s3:GetBucketLocation",
                    "s3:ListBucket",
                    "s3:PutBucketPolicy",
                    "s3:PutBucketTagging",
                    "s3:PutEncryptionConfiguration",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [f"arn:aws:s3:::{stack_name}-*"],
            }

    iam = {
                "Effect": "Allow",
                "Action": [
                    "iam:AddRoleToInstanceProfile",
                    "iam:AttachRolePolicy",
                    "iam:CreateInstanceProfile",
                    "iam:CreatePolicy",
                    "iam:CreateRole",
                    "iam:DeleteInstanceProfile",
                    "iam:DeletePolicy",
                    "iam:DeleteRole",
                    "iam:DeleteRolePolicy",
                    "iam:DetachRolePolicy",
                    "iam:GetInstanceProfile",
                    "iam:GetPolicy",
                    "iam:GetRole",
                    "iam:ListAttachedRolePolicies",
                    "iam:ListPolicyVersions",
                    "iam:PassRole",
                    "iam:PutRolePolicy",
                    "iam:RemoveRoleFromInstanceProfile",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [
                    f"arn:aws:iam::{aws_account_id}:policy/{stack_name}-*",
                    f"arn:aws:iam::{aws_account_id}:role/{stack_name}-*",
                    f"arn:aws:iam::{aws_account_id}:instance-profile/{stack_name}-*",
                ],
            }

    _lambda = {
                "Effect": "Allow",
                "Action": [
                    "lambda:CreateFunction",
                    "lambda:DeleteFunction",
                    "lambda:DeleteLayerVersion",
                    "lambda:GetFunction",
                    "lambda:GetLayerVersion",
                    "lambda:GetLayerVersionPolicy",
                    "lambda:InvokeFunction",
                    "lambda:PublishLayerVersion",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [
                    f"arn:aws:lambda:*:{aws_account_id}:function:{stack_name}-*",
                    f"arn:aws:lambda:*:{aws_account_id}:layer:*",
                ],
            }

    states = {
                "Effect": "Allow",
                "Action": [
                    "states:CreateStateMachine",
                    "states:DeleteStateMachine",
                    "states:TagResource",
                    "states:UntagResource",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [f"arn:aws:states:*:{aws_account_id}:stateMachine:Provider*"],
            }

    eks_nodegroups = {
                "Effect": "Allow",
                "Action": [
                    "eks:CreateNodegroup",
                    "eks:DeleteNodegroup",
                    "eks:DescribeNodegroup",
                    "eks:TagResource",
                    "eks:UntagResource",
                ],
                "Resource": [f"arn:aws:eks:*:{aws_account_id}:cluster/*"],
            }

    cfn_tagging = {
                "Effect": "Allow",
                "Action": [
                    "ssm:AddTagsToResource",
                    "ssm:DeleteParameter",
                    "ssm:PutParameter",
                    "ssm:RemoveTagsFromResource",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [f"arn:aws:ssm:*:{aws_account_id}:parameter/CFN*"],
            }

    ssm = {
                "Effect": "Allow",
                "Action": ["ssm:GetParameters"],
                "Resource": ["arn:aws:ssm:*::parameter/aws/service/eks/*"],
            }

    backup = {
                "Effect": "Allow",
                "Action": [
                    "backup:*BackupVault*",
                    "backup:CreateBackupPlan",
                    "backup:CreateBackupSelection",
                    "backup:DeleteBackupPlan",
                    "backup:DeleteBackupSelection",
                    "backup:GetBackupPlan",
                    "backup:GetBackupSelection",
                    "backup:ListTags",
                    "backup:TagResource",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [
                    f"arn:aws:backup:*:{aws_account_id}:backup-vault:{stack_name}-efs",
                    f"arn:aws:backup:*:{aws_account_id}:backup-plan:{stack_name}-efs",
                ],
            }

    general = {
                "Effect": "Allow",
                "Action": [
                    "autoscaling:CreateAutoScalingGroup",
                    "autoscaling:DeleteAutoScalingGroup",
                    "autoscaling:DescribeAutoScalingGroups",
                    "autoscaling:DescribeScalingActivities",
                    "autoscaling:UpdateAutoScalingGroup",
                    "backup-storage:MountCapsule",
                    "backup:*BackupPlan",
                    "backup:*BackupSelection",
                    "ec2:*NetworkInterface*",
                    "ec2:*Subnet*",
                    "ec2:AllocateAddress",
                    "ec2:AssociateRouteTable",
                    "ec2:AssociateVpcCidrBlock",
                    "ec2:AttachInternetGateway",
                    "ec2:AuthorizeSecurityGroupEgress",
                    "ec2:AuthorizeSecurityGroupIngress",
                    "ec2:CreateInternetGateway",
                    "ec2:CreateLaunchTemplate",
                    "ec2:CreateNatGateway",
                    "ec2:CreateRoute",
                    "ec2:CreateRouteTable",
                    "ec2:CreateSecurityGroup",
                    "ec2:CreateTags",
                    "ec2:CreateVpc",
                    "ec2:CreateVpcEndpoint",
                    "ec2:DeleteInternetGateway",
                    "ec2:DeleteLaunchTemplate",
                    "ec2:DeleteNatGateway",
                    "ec2:DeleteRoute",
                    "ec2:DeleteRouteTable",
                    "ec2:DeleteSecurityGroup",
                    "ec2:DeleteVpc",
                    "ec2:DeleteVpcEndpoints",
                    "ec2:DescribeAccountAttributes",
                    "ec2:DescribeAddresses",
                    "ec2:DescribeAddresses",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeInternetGateways",
                    "ec2:DescribeLaunchTemplates",
                    "ec2:DescribeNatGateways",
                    "ec2:DescribeRouteTables",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeVpcEndpoints",
                    "ec2:DescribeVpcs",
                    "ec2:DetachInternetGateway",
                    "ec2:DisAssociateRouteTable",
                    "ec2:DisassociateVpcCidrBlock",
                    "ec2:GetLaunchTemplateData",
                    "ec2:ModifyVpcAttribute",
                    "ec2:ReleaseAddress",
                    "ec2:RevokeSecurityGroupEgress",
                    "ec2:RevokeSecurityGroupIngress",
                    "ec2:RunInstances",
                    "eks:CreateNodegroup",
                    "eks:DeleteNodegroup",
                    "eks:DescribeNodegroup",
                    "eks:TagResource",
                    "eks:UntagResource",
                    "elasticfilesystem:Backup",
                    "elasticfilesystem:CreateAccessPoint",
                    "elasticfilesystem:CreateFileSystem",
                    "elasticfilesystem:CreateMountTarget",
                    "elasticfilesystem:DeleteAccessPoint",
                    "elasticfilesystem:DeleteFileSystem",
                    "elasticfilesystem:DeleteMountTarget",
                    "elasticfilesystem:DescribeAccessPoints",
                    "elasticfilesystem:DescribeFileSystems",
                    "elasticfilesystem:DescribeMountTargets",
                    "iam:GetRole",
                    "iam:ListAttachedRolePolicies",
                    "kms:CreateGrant",
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:GenerateDataKey",
                    "kms:RetireGrant",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": "*",
            }

#    from_cf_condition = {
#                    "ForAnyValue:StringEquals": {
#                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
#                    }
#                }

# if argv[1] == "cdk":
#     cloudformation["Resource"].append(f"arn:aws:cloudformation:*:{aws_account_id}:stack/CDKToolkit/*")
#     asset["Resource"].append("arn:aws:s3:::cdktoolkit-stagingbucket-*")
#     s3["Condition"] = from_cf_condition
#     iam["Condition"] = from_cf_condition
#     # TODO: eks_nodegroups is cdk specific
#     general["Condition"] = from_cf_condition

    base_iam = {
        "Version": "2012-10-17",
        "Statement": [cloudformation, asset_bucket, s3, iam, _lambda, states, eks_nodegroups, cfn_tagging, ssm, backup, general]
    }

    tf_iam = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "cloudformation:CreateChangeSet",
                    "cloudformation:DeleteChangeSet",
                    "cloudformation:DeleteStack",
                    "cloudformation:DescribeChangeSet",
                    "cloudformation:DescribeStackEvents",
                    "cloudformation:DescribeStacks",
                    "cloudformation:ExecuteChangeSet",
                    "cloudformation:GetTemplate",
                ],
                "Resource": [
                    f"arn:aws:cloudformation:*:{aws_account_id}:stack/{stack_name}-*"
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["s3:*Object", "s3:GetBucketLocation", "s3:ListBucket"],
                "Resource": ["arn:aws:s3:::*"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:CreateBucket",
                    "s3:DeleteBucket",
                    "s3:DeleteBucketPolicy",
                    "s3:GetBucketLocation",
                    "s3:ListBucket",
                    "s3:PutBucketPolicy",
                    "s3:PutBucketTagging",
                    "s3:PutEncryptionConfiguration",
                ],
                "Resource": [f"arn:aws:s3:::{stack_name}-*"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "iam:AddRoleToInstanceProfile",
                    "iam:AttachRolePolicy",
                    "iam:CreateInstanceProfile",
                    "iam:CreatePolicy",
                    "iam:CreateRole",
                    "iam:DeleteInstanceProfile",
                    "iam:DeletePolicy",
                    "iam:DeleteRole",
                    "iam:DeleteRolePolicy",
                    "iam:DetachRolePolicy",
                    "iam:GetInstanceProfile",
                    "iam:GetPolicy",
                    "iam:ListAttachedRolePolicies",
                    "iam:ListPolicyVersions",
                    "iam:PassRole",
                    "iam:PutRolePolicy",
                    "iam:RemoveRoleFromInstanceProfile",
                    "iam:Tag*",
                    "iam:Untag*",
                ],
                "Resource": [
                    f"arn:aws:iam::{aws_account_id}:policy/{stack_name}-*",
                    f"arn:aws:iam::{aws_account_id}:role/{stack_name}-*",
                    f"arn:aws:iam::{aws_account_id}:instance-profile/{stack_name}-*",
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": [
                    f"arn:aws:lambda:*:{aws_account_id}:function:{stack_name}-*"
                ],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "lambda:CreateFunction",
                    "lambda:DeleteFunction",
                    "lambda:DeleteLayerVersion",
                    "lambda:GetFunction",
                    "lambda:GetLayerVersion",
                    "lambda:GetLayerVersionPolicy",
                    "lambda:InvokeFunction",
                    "lambda:PublishLayerVersion",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [
                    f"arn:aws:lambda:*:{aws_account_id}:function:{stack_name}-*",
                    f"arn:aws:lambda:*:{aws_account_id}:layer:*",
                ],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "states:CreateStateMachine",
                    "states:DeleteStateMachine",
                    "states:TagResource",
                    "states:UntagResource",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [f"arn:aws:states:*:{aws_account_id}:stateMachine:Provider*"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ssm:AddTagsToResource",
                    "ssm:DeleteParameter",
                    "ssm:PutParameter",
                    "ssm:RemoveTagsFromResource",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [f"arn:aws:ssm:*:{aws_account_id}:parameter/CFN*"],
            },
            {
                "Effect": "Allow",
                "Action": ["ssm:GetParameters"],
                "Resource": ["arn:aws:ssm:*::parameter/aws/service/eks/*"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "backup:*BackupPlan",
                    "backup:*BackupVault*",
                    "backup:CreateBackupSelection",
                    "backup:DeleteBackupSelection",
                    "backup:GetBackupSelection",
                    "backup:ListTags",
                    "backup:TagResource",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [
                    f"arn:aws:backup:*:{aws_account_id}:backup-vault:{stack_name}-efs",
                    f"arn:aws:backup:*:{aws_account_id}:backup-plan:*",
                ],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "backup-storage:MountCapsule",
                    "elasticfilesystem:CreateAccessPoint",
                    "elasticfilesystem:CreateFileSystem",
                    "elasticfilesystem:DeleteAccessPoint",
                    "elasticfilesystem:DeleteFileSystem",
                    "elasticfilesystem:DescribeAccessPoints",
                    "elasticfilesystem:DescribeFileSystems",
                    "kms:CreateGrant",
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:GenerateDataKey",
                    "kms:RetireGrant",
                ],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": ["ecr:CreateRepository", "ecr:DeleteRepository"],
                "Condition": {
                    "ForAnyValue:StringEquals": {
                        "aws:CalledVia": ["cloudformation.amazonaws.com"]
                    }
                },
                "Resource": [f"arn:aws:ecr:*:{aws_account_id}:repository/{stack_name}*"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "autoscaling:CreateAutoScalingGroup",
                    "autoscaling:DeleteAutoScalingGroup",
                    "autoscaling:DescribeAutoScalingGroups",
                    "autoscaling:DescribeScalingActivities",
                    "autoscaling:UpdateAutoScalingGroup",
                    "ec2:*InternetGateway*",
                    "ec2:*NatGateway*",
                    "ec2:*NetworkInterface*",
                    "ec2:*Route*",
                    "ec2:*SecurityGroupEgress",
                    "ec2:*SecurityGroupIngress",
                    "ec2:*Subnet*",
                    "ec2:*Vpc*",
                    "ec2:AllocateAddress",
                    "ec2:CreateLaunchTemplate",
                    "ec2:CreateSecurityGroup",
                    "ec2:CreateTags",
                    "ec2:DeleteLaunchTemplate",
                    "ec2:DeleteSecurityGroup",
                    "ec2:DescribeAccountAttributes",
                    "ec2:DescribeAddresses",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeLaunchTemplates",
                    "ec2:DescribeSecurityGroups",
                    "ec2:GetLaunchTemplateData",
                    "ec2:ReleaseAddress",
                    "ec2:RunInstances",
                    "eks:CreateNodegroup",
                    "eks:DeleteNodegroup",
                    "eks:DescribeNodegroup",
                    "eks:TagResource",
                    "eks:UntagResource",
                    "elasticfilesystem:Backup",
                    "elasticfilesystem:CreateMountTarget",
                    "elasticfilesystem:DeleteMountTarget",
                    "elasticfilesystem:DescribeMountTargets",
                    "iam:GetRole",
                    "s3:GetBucketLocation",
                    "s3:GetObject",
                    "s3:ListBucket",
                ],
                "Resource": ["*"],
            },
        ],
    }

    if terraform:
        return tf_iam
    else:
        return base_iam