from os import path
from re import MULTILINE
from re import split as re_split

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import requests
from aws_cdk import core as cdk
from yaml import safe_load as yaml_safe_load

from .provisioners.lambda_utils import helm_lambda

dirname = path.dirname(path.abspath(__file__))

manifests = [
    {
        "vendored": path.join(dirname, "manifests", "calico.yaml"),  # in cwd
        "alternative_url": "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml",
    },
]


class DominoAwsConfigurator:
    def __init__(self, scope: cdk.Construct, eks_cluster: eks.Cluster, vpc: ec2.Vpc):
        self.scope = scope
        self.eks_cluster = eks_cluster
        self.vpc = vpc

        self._install_calico_helm_lambda()

    def install_calico(self):
        for manifest in manifests:
            filename = manifest["vendored"]
            if path.isfile(filename):
                with open(filename) as f:
                    manifest_text = f.read()
            else:
                manifest_text = requests.get(manifest["alternative_url"]).text
            loaded_manifests = [yaml_safe_load(i) for i in re_split("^---$", manifest_text, flags=MULTILINE) if i]
            crds = eks.KubernetesManifest(
                self.scope,
                "calico-crds",
                cluster=self.eks_cluster,
                manifest=[crd for crd in loaded_manifests if crd["kind"] == "CustomResourceDefinition"],
            )
            non_crds = eks.KubernetesManifest(
                self.scope,
                "calico",
                cluster=self.eks_cluster,
                manifest=[notcrd for notcrd in loaded_manifests if notcrd["kind"] != "CustomResourceDefinition"],
            )
            non_crds.node.add_dependency(crds)

    def _install_calico_helm_lambda(self):
        helm_lambda(scope=self.scope, name="install_calico", cluster=self.eks_cluster, vpc=self.vpc)
