from io import StringIO
from os.path import isfile
from pathlib import Path

import aws_cdk.aws_eks as eks
from aws_cdk import core as cdk
from requests import get as requests_get
from ruamel.yaml import YAML

manifests = [
    (
        "calico-operator",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.11.0/config/master/calico-operator.yaml",
    ),
    (
        "calico-crs",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.11.0/config/master/calico-crs.yaml",
    ),
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

    def install_calico(self):
        # This produces an obnoxious diff on every subsequent run
        # Using a helm chart does not, so we should switch to that
        # However, we need to figure out how to get the helm chart
        # accessible by the CDK lambda first. Not clear how to give
        # s3 perms to it programmatically, and while ECR might be
        # an option it also doesn't seem like there's a way to push
        # the chart with existing api calls.
        # Probably need to do some custom lambda thing.

        crd_manifests = []
        notcrd_manifests = []

        for (name, url) in manifests:
            filename = f"{name}.yaml"
            if isfile(filename):
                stream = Path(filename)
            else:
                stream = StringIO(requests_get(url).text)

            yaml = YAML(typ="safe")
            loaded_manifests = list(yaml.load_all(stream))

            crd_manifests += [crd for crd in loaded_manifests if crd["kind"] == "CustomResourceDefinition"]
            notcrd_manifests += [notcrd for notcrd in loaded_manifests if notcrd["kind"] != "CustomResourceDefinition"]

        # NB: be careful changing resource names or removing the manifests as prune is set by default
        # and could inadvertantly remove other resources if deleted after the new manifest is created

        # Split CRDs into multiple manifests so they don't go over the lambda limit of 262144 bytes
        crds = []
        for i, crd in enumerate(crd_manifests):
            crds.append(
                eks.KubernetesManifest(
                    self.scope,
                    # See above note about changing resource names
                    "calico-crds" + ("" if i == 0 else str(i)),
                    cluster=self.eks_cluster,
                    manifest=[crd],
                    overwrite=True,
                )
            )

        if notcrd_manifests:
            non_crds = eks.KubernetesManifest(
                self.scope, "calico", cluster=self.eks_cluster, manifest=notcrd_manifests, overwrite=True
            )

            for crd in crds:
                non_crds.node.add_dependency(crd)
