#!/usr/bin/env python3
from enum import Enum

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
    eks_nodegroup = "AWS::EKS::Nodegroup"
    endpoint = "AWS::EC2::VPCEndpoint"
    iam_policy = "AWS::IAM::ManagedPolicy"
    iam_role = "AWS::IAM::Role"
    instance = "AWS::EC2::Instance"
    instance_profile = "AWS::IAM::InstanceProfile"
    lambda_function = "AWS::Lambda::Function"
    lambda_layerversion = "AWS::Lambda::LayerVersion"
    launch_template = "AWS::EC2::LaunchTemplate"
    security_group = "AWS::EC2::SecurityGroup"
    security_group_rule_ids = "security_group_rule_ids"  # special
    ssm_parameter = "AWS::SSM::Parameter"
    stepfunctions_statemachine = "AWS::StepFunctions::StateMachine"
