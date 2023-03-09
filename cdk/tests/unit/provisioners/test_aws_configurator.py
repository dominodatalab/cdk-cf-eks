import aws_cdk.aws_eks as eks
from aws_cdk.assertions import Template
from aws_cdk.core import App, Environment, Stack

from domino_cdk.aws_configurator import DominoAwsConfigurator

from . import TestCase


class TestDominoAwsConfigurator(TestCase):
    def setUp(self):
        self.app = App()
        self.stack = Stack(self.app, "calico", env=Environment(region="us-west-2"))
        self.eks_cluster = eks.Cluster(self.stack, "eks", version=eks.KubernetesVersion.V1_21)

    def test_install_calico(self):
        DominoAwsConfigurator(self.stack, self.eks_cluster)

        assertion = Template.from_stack(self.stack)
        assertion.resource_count_is("Custom::AWSCDK-EKS-HelmChart", 1)
