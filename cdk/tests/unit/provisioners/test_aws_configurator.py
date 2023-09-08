from json import loads
from os import chdir
from tempfile import TemporaryDirectory

import aws_cdk.aws_eks as eks
from aws_cdk import App, Environment, Stack
from aws_cdk.assertions import Template
from ruamel.yaml import YAML

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
        assertion.resource_count_is("Custom::AWSCDK-EKS-KubernetesResource", 21)  # 20 calico, one aws-auth

        template = self.app.synth().get_stack("calico").template

        crds_resource = next(res for name, res in template["Resources"].items() if name.startswith("calicocrds"))
        self.assertTrue(len(loads(crds_resource["Properties"]["Manifest"])) > 0)

        noncrds_resource = next(
            res for name, res in template["Resources"].items() if name.startswith("calico") and res != crds_resource
        )
        self.assertTrue(len(loads(noncrds_resource["Properties"]["Manifest"])) > 0)

    def test_install_calico_file(self):
        with TemporaryDirectory() as tmpdir:
            chdir(tmpdir)

            with open("calico-operator.yaml", "w+") as f:
                YAML().dump_all([{"kind": "DaemonSet", "apiVersion": "apps/v1", "metadata": {"name": "test-ds"}}], f)

            DominoAwsConfigurator(self.stack, self.eks_cluster)

        assertion = Template.from_stack(self.stack)
        assertion.resource_count_is("Custom::AWSCDK-EKS-KubernetesResource", 2)  # two calico, one aws-auth

        template = self.app.synth().get_stack("calico").template

        crds_resource = next(
            (res for name, res in template["Resources"].items() if name.startswith("calicocrds")), None
        )
        self.assertIsNone(crds_resource)

        noncrds_resource = next(
            res for name, res in template["Resources"].items() if name.startswith("calico") and res != crds_resource
        )
        self.assertEqual(len(loads(noncrds_resource["Properties"]["Manifest"])), 2)
