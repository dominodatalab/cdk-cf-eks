#!/usr/bin/env python3
from enum import Enum

resource_template = {
    "efs_stack": [
        {"cf": "Efs", "tf": "module.domino_eks.module.storage.aws_efs_file_system.eks"},
        {
            "cf": "Efsaccesspoint",
            "tf": "module.domino_eks.module.storage.aws_efs_access_point.eks",
        },
    ],
    "eks_stack": [
        {"cf": "eks", "tf": "module.domino_eks.module.eks.aws_eks_cluster.this"},
        {
            "cf": "EKSSG",
            "tf": "module.domino_eks.module.eks.aws_security_group.eks_cluster",
        },
        {
            "cf_sgr": {
                "sg": "EKSSG",
                "rule": "_egress_tcp_443_443_",
                "rule_sg": "UnmanagedSG",
            },
            "tf": 'module.domino_eks.module.eks.aws_security_group_rule.eks_cluster["egress_nodes_443"]',
        },
        {
            "cf_sgr": {
                "sg": "EKSSG",
                "rule": "_ingress_tcp_443_443_",
                "rule_sg": "UnmanagedSG",
            },
            "tf": 'module.domino_eks.module.eks.aws_security_group_rule.eks_cluster["ingress_nodes_443"]',
        },
        {
            "cf": "UnmanagedSG",
            "tf": "module.domino_eks.module.eks.aws_security_group.eks_nodes",
        },
        {
            "cf_sgr": {
                "sg": "UnmanagedSG",
                "rule": "_ingress_tcp_443_443_",
                "rule_sg": "EKSSG",
            },
            "tf": 'module.domino_eks.module.eks.aws_security_group_rule.node["ingress_cluster_443"]',
        },
        {
            "cf_sgr": {
                "sg": "UnmanagedSG",
                "rule": "_ingress_tcp_22_22_",
                "rule_sg": "bastionsg",
                "rule_sg_stack": "vpc_stack",
            },
            "tf": 'module.domino_eks.module.eks.aws_security_group_rule.bastion_eks["eks_nodes_ssh_from_bastion"]',
        },
        {
            "cf": "eksRole",
            "tf": "module.domino_eks.module.eks.aws_iam_role.eks_cluster",
        },
        {
            "tf": "module.domino_eks.module.eks.aws_cloudwatch_log_group.eks_cluster",
            "value": "/aws/eks/%stack_name%/cluster",
        },
        {"cf": "S3", "tf": "module.domino_eks.module.storage.aws_iam_policy.s3"},
        {
            "tf": 'module.domino_eks.module.eks.aws_eks_addon.this["coredns"]',
            "value": "%stack_name%:coredns",
        },
        {
            "tf": "module.domino_eks.module.eks.aws_eks_addon.vpc_cni",
            "value": "%stack_name%:vpc-cni",
        },
        {
            "tf": 'module.domino_eks.module.eks.aws_eks_addon.this["kube-proxy"]',
            "value": "%stack_name%:kube-proxy",
        },
        {
            "cf": "eksCreationRole",
            "tf": "aws_iam_role.grandfathered_creation_role",
        },
        {
            "cf": "%stack_name%kubernetessecretsenvelopekey",
            "tf": "module.domino_eks.module.eks.aws_kms_key.eks_cluster",
        },
    ],
    "s3_stack": [
        {
            "cf": "backups",
            "tf": "module.domino_eks.module.storage.aws_s3_bucket.backups",
        },
        {"cf": "blobs", "tf": "module.domino_eks.module.storage.aws_s3_bucket.blobs"},
        {"cf": "logs", "tf": "module.domino_eks.module.storage.aws_s3_bucket.logs"},
        {
            "cf": "registry",
            "tf": "module.domino_eks.module.storage.aws_s3_bucket.registry",
        },
        {
            "cf": "monitoring",
            "tf": "module.domino_eks.module.storage.aws_s3_bucket.monitoring",
        },
    ],
    "vpc_stack": [
        {
            "cf": "bastionsg",
            "tf": "module.domino_eks.module.bastion[0].aws_security_group.bastion",
        },
        {
            "cf_sgr": {
                "sg": "bastionsg",
                "rule": "_egress_all_0_0_0.0.0.0/0",
            },
            "tf": "module.domino_eks.module.bastion[0].aws_security_group_rule.bastion_outbound",
        },
        {
            "cf_sgr": {
                "sg": "bastionsg",
                "rule": "_ingress_tcp_22_22_0.0.0.0/0",
            },
            "tf": 'module.domino_eks.module.bastion[0].aws_security_group_rule.bastion["bastion_inbound_ssh"]',
        },
        {
            "cf": "VPC",
            "tf": "aws_vpc.cdk_vpc",
        },
        {
            "cf": "VPCIGW",
            "tf": "aws_internet_gateway.cdk_vpc",
        },
        {
            "cf_igw_attachment": {
                "igw": "VPCIGW",
                "vpc": "VPC",
            },
            "tf": "aws_internet_gateway_attachment.cdk_vpc",
        },
    ],
}

efs_backup_resources = [
    {
        "cf": "efsbackup",
        "tf": "module.domino_eks.module.storage.aws_backup_vault.efs[0]",
    },
    {
        "cf": "efsbackupplan",
        "tf": "module.domino_eks.module.storage.aws_backup_plan.efs[0]",
    },
    {
        "cf": "efsbackuprole",
        "tf": "module.domino_eks.module.storage.aws_iam_role.efs_backup_role[0]",
    },
    {"cf_backupselection": "efsbackupselection", "tf": "module.domino_eks.module.storage.aws_backup_selection.efs[0]"},
]

route53_resource = {"cf": "route53", "tf": "module.domino_eks.aws_iam_policy.route53[0]"}

stack_map = {
    "EfsStackNestedStackEfsStackNestedStackResource": "efs_stack",
    "EksStackNestedStackEksStackNestedStackResource": "eks_stack",
    "S3StackNestedStackS3StackNestedStackResource": "s3_stack",
    "VpcStackNestedStackVpcStackNestedStackResource": "vpc_stack",
    "awscdkawseksKubectlProviderNestedStackawscdkawseksKubectlProviderNestedStackResource": "kubectl_stack",
    "awscdkawseksClusterResourceProviderNestedStackawscdkawseksClusterResourceProviderNestedStackResource": "cluster_stack",
}

cf_status = [
    "CREATE_IN_PROGRESS",
    "CREATE_FAILED",
    "CREATE_COMPLETE",
    "ROLLBACK_IN_PROGRESS",
    "ROLLBACK_FAILED",
    "ROLLBACK_COMPLETE",
    "DELETE_IN_PROGRESS",
    "DELETE_FAILED",
    "UPDATE_IN_PROGRESS",
    "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
    "UPDATE_COMPLETE",
    "UPDATE_FAILED",
    "UPDATE_ROLLBACK_IN_PROGRESS",
    "UPDATE_ROLLBACK_FAILED",
    "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS",
    "UPDATE_ROLLBACK_COMPLETE",
    "REVIEW_IN_PROGRESS",
    "IMPORT_IN_PROGRESS",
    "IMPORT_COMPLETE",
    "IMPORT_ROLLBACK_IN_PROGRESS",
    "IMPORT_ROLLBACK_FAILED",
    "IMPORT_ROLLBACK_COMPLETE",
    "DELETE_COMPLETE",
]


class cdk_ids(Enum):
    asg = "AWS::AutoScaling::AutoScalingGroup"
    cloudformation_stack = "AWS::CloudFormation::Stack"
    eip = "AWS::EC2::EIP"
    flowlog = "AWS::EC2::FlowLog"
    instance = "AWS::EC2::Instance"
    launch_template = "AWS::EC2::LaunchTemplate"
    security_group = "AWS::EC2::SecurityGroup"
    instance_profile = "AWS::IAM::InstanceProfile"
    iam_policy = "AWS::IAM::ManagedPolicy"
    iam_role = "AWS::IAM::Role"
    lambda_function = "AWS::Lambda::Function"
    stepfunctions_statemachine = "AWS::StepFunctions::StateMachine"
    lambda_layerversion = "AWS::Lambda::LayerVersion"
    ssm_parameter = "AWS::SSM::Parameter"
