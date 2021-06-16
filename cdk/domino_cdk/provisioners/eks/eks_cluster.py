import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
from aws_cdk import core as cdk


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

        # Note: We can't tag the EKS cluster via CDK/CF: https://github.com/aws/aws-cdk/issues/4995
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
