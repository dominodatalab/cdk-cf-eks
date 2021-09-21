from json import loads
from unittest.mock import patch

import aws_cdk.aws_eks as eks
from aws_cdk.assertions import Template
from aws_cdk.core import App, Environment, Stack

from domino_cdk.provisioners.eks import DominoEksClusterProvisioner

from . import TestCase

STACK_NAME = "DominoCDK"
ADDON_VERSION = "1.2.3-x.y.z"


class TestEksClusterProvisioner(TestCase):
    def setUp(self):
        self.app = App()
        self.stack = Stack(self.app, STACK_NAME, env=Environment(region="us-west-2"))
        self.eks_version = eks.KubernetesVersion.V1_20
        self.eks_cluster = eks.Cluster(self.stack, "eks", version=self.eks_version)

    @patch("domino_cdk.provisioners.eks.DominoEksClusterProvisioner._get_addon_version")
    def test_setup_addons(self, mock_get_addon_version):
        mock_get_addon_version.return_value = ADDON_VERSION

        eks_provisioner = DominoEksClusterProvisioner(self.stack)

        eks_provisioner.setup_addons(self.eks_cluster, self.eks_version.version)

        assertion = Template.from_stack(self.stack)
        assertion.resource_count_is("Custom::AWSCDK-EKS-KubernetesPatch", 1)
        assertion.resource_count_is("AWS::EKS::Addon", 3)
        assertion.has_resource_properties("AWS::EKS::Addon", {"AddonName": "vpc-cni", "AddonVersion": ADDON_VERSION})
        assertion.has_resource_properties("AWS::EKS::Addon", {"AddonName": "kube-proxy", "AddonVersion": ADDON_VERSION})
        assertion.has_resource_properties("AWS::EKS::Addon", {"AddonName": "coredns", "AddonVersion": ADDON_VERSION})

        template = self.app.synth().get_stack(STACK_NAME).template

        k8s_patch = self.find_resource(template, "Custom::AWSCDK-EKS-KubernetesPatch")
        properties = k8s_patch["Properties"]

        self.assertEqual("daemonset/aws-node", properties["ResourceName"])
        self.assertEqual(
            {"spec": {"template": {"spec": {"securityContext": {"seLinuxOptions": {"type": "spc_t"}}}}}},
            loads(properties["ApplyPatchJson"]),
        )
        self.assertEqual("{}", properties["RestorePatchJson"])
        self.assertEqual("strategic", properties["PatchType"])
