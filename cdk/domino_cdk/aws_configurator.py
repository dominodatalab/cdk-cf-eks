from aws_cdk import aws_eks as eks
from aws_cdk import core as cdk


class DominoAwsConfigurator:
    def __init__(self, scope: cdk.Construct, eks_cluster: eks.Cluster):
        self.scope = scope
        self.eks_cluster = eks_cluster

        self.install_calico()

    def install_calico(self):
        eks.HelmChart(
            scope=self.scope,
            id="calico-helm-chart",
            cluster=self.eks_cluster,
            chart="tigera-operator",
            repository="https://docs.tigera.io/calico/charts",
            create_namespace=True,
            namespace="tigera-operator",
            values={"installation": {"kubernetesProvider": "EKS"}},
            release="calico-tigera-operator",
            version="v3.25.0",
            timeout=cdk.Duration.minutes(10),
            wait=True,
        )
