import aws_cdk.aws_eks as eks
import aws_cdk.core as cdk


class DominoAwsConfigurator:
    def __init__(self, scope: cdk.Construct, eks_cluster: eks.Cluster):
        self.scope = scope
        self.eks_cluster = eks_cluster

        self.install_calico()

    def install_calico(self):
        # The following implementation is a workround Cloud Formation life-cycle limitations.
        # The actual change is to install the calico-operator using the helm-chart, due to the fact
        # that on version v3.25.0 of the tigera-operator manifest the CRD `installations.operator.tigera.io`
        # is surpasses the lambda limit event size limit causing the following error:
        # `357330 byte payload is too large for the Event invocation type (limit 262144 bytes)`.
        # Therefore he only option is to install it using the helm-chart. but
        # At the same time we need to support upgrades, and simply replacing the multiple `KubernetesManifest` with
        # the `HelmChart` produces an error since the helm-chart is applied before the k8s objects are deleted and helm tries to create resources
        # that already exist.
        # Since we need to replace them with `something`(manifest can not be []) to replace the CRDs and installation we are using a
        # configmap(`not-used`). As well as adding the creation as a dependency to the `HelmChart`.
        # As a result the k8s objects get deleted and replaced with a configmap then the `HelmChart` can install successfully.

        replace_calico_install = eks.KubernetesManifest(
            self.scope,
            "calico",
            cluster=self.eks_cluster,
            manifest=[{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "not-used"}}],
            overwrite=True,
        )

        replace_calico_crds = []
        # This will recreate a configmap 20 times to replace the previous calico crds
        for i in range(19):
            manifest = eks.KubernetesManifest(
                self.scope,
                "calico-crds" + ("" if i == 0 else str(i)),
                cluster=self.eks_cluster,
                manifest=[{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "not-used"}}],
                overwrite=True,
            )
            manifest.node.add_dependency(replace_calico_install)
            replace_calico_crds.append(manifest)

        calico_helm_chart = eks.HelmChart(
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
        )
        calico_helm_chart.node.add_dependency(replace_calico_crds[-1])
