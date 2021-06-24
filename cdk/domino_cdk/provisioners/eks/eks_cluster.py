import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_logs as logs
import aws_cdk.custom_resources as cr
from aws_cdk import core as cdk
from aws_cdk.aws_kms import Key


class DominoEksClusterProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
    ) -> None:
        self.scope = scope

    def provision(
        self,
        name: str,
        eks_version: eks.KubernetesVersion,
        private_api: bool,
        secrets_encryption_key_arn: str,
        vpc: ec2.Vpc,
        bastion_sg: ec2.SecurityGroup,
    ):
        eks_sg = ec2.SecurityGroup(
            self.scope,
            "EKSSG",
            vpc=vpc,
            security_group_name=f"{name}-EKSSG",
            allow_all_outbound=False,
        )

        if secrets_encryption_key_arn:
            key = Key.from_key_arn(self.scope, "secrets_encryption_key_arn", secrets_encryption_key_arn)
        else:
            key = Key(
                self.scope,
                f"{name}-kubernetes-secrets-envelope-key",
                alias=f"{name}-kubernetes-secrets-envelope-key",
                removal_policy=cdk.RemovalPolicy.DESTROY,
                enable_key_rotation=True,
            )

        # TODO: tag the EKS cluster
        # Need some way: https://github.com/aws/aws-cdk/issues/4995
        
        cluster = eks.Cluster(
            self.scope,
            "eks",
            cluster_name=name,
            vpc=vpc,
            endpoint_access=eks.EndpointAccess.PRIVATE if private_api else None,
            vpc_subnets=[ec2.SubnetType.PRIVATE],
            version=eks_version,
            default_capacity=0,
            security_group=eks_sg,
            secrets_encryption_key=key,
        )

        params = {
            "name": cluster.cluster_name,
            "logging": {
                "clusterLogging": [
                    {
                        "enabled": True,
                        "types": ["api", "audit", "authenticator", "controllerManager", "scheduler"],
                    },
                ],
            },
        }

        cr.AwsCustomResource(
            self.scope,
            "UpdateClusterConfigCustom",
            timeout=cdk.Duration.minutes(10),  # defaults to 2 minutes
            log_retention=logs.RetentionDays.ONE_DAY,  # defaults to never delete logs
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            on_create={
                "service": "EKS",
                "action": "updateClusterConfig",
                "parameters": params,
                "physical_resource_id": cr.PhysicalResourceId.of("UpdateClusterConfigCustom"),
                "ignore_error_codes_matching": "...",
            },
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

        cdk.CfnOutput(self.scope, "eks_cluster_name", value=cluster.cluster_name)
        cdk.CfnOutput(
            self.scope,
            "eks_kubeconfig_cmd",
            value=f"aws eks update-kubeconfig --name {cluster.cluster_name} --region {self.scope.region} --role-arn {cluster.kubectl_role.role_arn}",
        )

        return cluster
