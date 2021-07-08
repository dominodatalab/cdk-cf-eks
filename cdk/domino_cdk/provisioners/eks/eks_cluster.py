import json
from os import path
from typing import Dict

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
from aws_cdk import core as cdk
from aws_cdk.aws_kms import Key
from aws_cdk.region_info import Fact, FactName

from ..lambda_utils import create_lambda


class DominoEksClusterProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
    ) -> None:
        self.scope = scope

    def provision(
        self,
        stack_name: str,
        eks_version: eks.KubernetesVersion,
        private_api: bool,
        secrets_encryption_key_arn: str,
        vpc: ec2.Vpc,
        bastion_sg: ec2.SecurityGroup,
        tags: Dict[str, str],
    ) -> eks.Cluster:
        partition = Fact.require_fact(self.scope.region, FactName.PARTITION)

        eks_sg = ec2.SecurityGroup(
            self.scope,
            "EKSSG",
            vpc=vpc,
            security_group_name=f"{stack_name}-EKSSG",
            allow_all_outbound=False,
        )

        if secrets_encryption_key_arn:
            key = Key.from_key_arn(self.scope, "secrets_encryption_key_arn", secrets_encryption_key_arn)
        else:
            key = Key(
                self.scope,
                f"{stack_name}-kubernetes-secrets-envelope-key",
                alias=f"{stack_name}-kubernetes-secrets-envelope-key",
                removal_policy=cdk.RemovalPolicy.DESTROY,
                enable_key_rotation=True,
            )

        log_cleanup = create_lambda(
            scope=self.scope,
            stack_name=stack_name,
            name="cluster_post_deletion_tasks",
            environment={
                "cluster": stack_name,
            },
            resources=[
                f"arn:{partition}:logs:{self.scope.region}:{self.scope.account}:log-group:/aws/lambda/{stack_name}*",
                f"arn:{partition}:logs:{self.scope.region}:{self.scope.account}:log-group:*:log-stream:*",
            ],
            actions=[
                "logs:DescribeLogGroups",
                "logs:PutRetentionPolicy",
            ],
        )

        cluster = eks.Cluster(
            self.scope,
            "eks",
            cluster_name=stack_name,
            vpc=vpc,
            endpoint_access=eks.EndpointAccess.PRIVATE if private_api else None,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE)],
            version=eks_version,
            default_capacity=0,
            security_group=eks_sg,
            secrets_encryption_key=key,
        )

        cluster.node.add_dependency(log_cleanup)  # make sure log cleanup is called after cluster cleanup

        create_lambda(
            scope=self.scope,
            stack_name=stack_name,
            name="cluster_post_creation_tasks",
            environment={
                "cluster": cluster.cluster_name,
                "cluster_arn": cluster.cluster_arn,
                "tags": json.dumps(tags),
            },
            resources=[
                f"arn:{partition}:logs:{self.scope.region}:{self.scope.account}:log-group:/aws/eks/{cluster.cluster_name}/cluster",
                cluster.cluster_arn + "*",
                f"arn:{partition}:logs:{self.scope.region}:{self.scope.account}:log-group:*:log-stream:*",
            ],
            actions=[
                "logs:DescribeLogGroups",
                "logs:PutRetentionPolicy",
                "eks:TagResource",
                "eks:UpdateClusterConfig",
            ],
        )

        if bastion_sg:
            cluster.cluster_security_group.add_ingress_rule(
                peer=bastion_sg,
                connection=ec2.Port(
                    protocol=ec2.Protocol("TCP"),
                    string_representation="API Access",
                    from_port=443,
                    to_port=443,
                ),
            )

        return cluster
