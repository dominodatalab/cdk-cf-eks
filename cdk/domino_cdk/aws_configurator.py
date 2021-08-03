from io import StringIO
from os.path import isfile
from pathlib import Path

import aws_cdk.aws_eks as eks
from aws_cdk import core as cdk
from requests import get as requests_get
from ruamel.yaml import YAML

manifests = [
    (
        "calico",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml",
    )
]


# Currently this just installs calico directly via manifest, but will
# ultimately become a lambda that handles various tasks (calico,
# deprovisoning efs backups/route53, tagging the eks cluster until
# the CloudFormation api supports it, etc.)
class DominoAwsConfigurator:
    def __init__(self, scope: cdk.Construct, eks_cluster: eks.Cluster):
        self.scope = scope
        self.eks_cluster = eks_cluster

        self.install_calico()
        self.patch_vpc_cni_selinux()

    def install_calico(self):
        # This produces an obnoxious diff on every subsequent run
        # Using a helm chart does not, so we should switch to that
        # However, we need to figure out how to get the helm chart
        # accessible by the CDK lambda first. Not clear how to give
        # s3 perms to it programmatically, and while ECR might be
        # an option it also doesn't seem like there's a way to push
        # the chart with existing api calls.
        # Probably need to do some custom lambda thing.
        for (name, url) in manifests:
            filename = f"{name}.yaml"
            if isfile(filename):
                stream = Path(filename)
            else:
                stream = StringIO(requests_get(url).text)

            yaml = YAML(typ="safe")
            loaded_manifests = list(yaml.load_all(stream))

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

    # Until https://github.com/aws/amazon-vpc-cni-k8s/issues/1291 is resolved
    def patch_vpc_cni_selinux(self):
        eks.KubernetesPatch(
            self.scope,
            "vpc-cni-selinux",
            cluster=self.eks_cluster,
            resource_name="daemonset/aws-node",
            resource_namespace="kube-system",
            apply_patch={"spec": {"template": {"spec": {"securityContext": {"seLinuxOptions": {"type": "spc_t"}}}}}},
            restore_patch={},
        )
