from os.path import isfile
from re import MULTILINE
from re import split as re_split
from typing import Any, List, Optional, Tuple, Type, Union

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as aws_lambda
from aws_cdk import aws_autoscaling
from aws_cdk import core as cdk
from aws_cdk.lambda_layer_awscli import AwsCliLayer
from aws_cdk.lambda_layer_kubectl import KubectlLayer
from requests import get as requests_get
from yaml import safe_load as yaml_safe_load

from domino_cdk.config.eks import EKS
from domino_cdk.config.util import MachineImage

manifests = [
    [
        "calico",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml",
    ]
]


class ExternalCommandException(Exception):
    """Exception running spawned external commands"""


class DominoEksStack(cdk.NestedStack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        name: str,
        eks_cfg: EKS,
        vpc: ec2.Vpc,
        private_subnet_name: str,
        bastion_sg: ec2.SecurityGroup,
        r53_zone_ids: List[str],
        s3_policy: iam.ManagedPolicy,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # TODO: Don't forget to refactor/aggregate/something outputs too
        self.outputs = {}
        self.name = name
        self.eks_cfg = eks_cfg
        self.vpc = vpc
        self.private_subnet_name = private_subnet_name
        self.bastion_sg = bastion_sg

        self.eks_version = eks.KubernetesVersion.V1_19

        self.provision_eks_cluster()
        self.provision_eks_iam_policies(s3_policy, r53_zone_ids)

        max_nodegroup_azs = self.eks_cfg.max_nodegroup_azs

        for name, ng in self.eks_cfg.managed_nodegroups.items():
            if not ng.machine_image or not ng.machine_image.ami_id:
                ng.labels = {**ng.labels, **self.eks_cfg.global_node_labels}
                ng.tags = {
                    **ng.tags,
                    **self.eks_cfg.global_node_tags,
                    **{f"k8s.io/cluster-autoscaler/node-template/label/{k}": v for k, v in ng.labels.items()},
                }
            self.provision_managed_nodegroup(name, ng, max_nodegroup_azs)

        for name, ng in self.eks_cfg.unmanaged_nodegroups.items():
            if not ng.machine_image or not ng.machine_image.ami_id:
                ng.labels = {**ng.labels, **self.eks_cfg.global_node_labels}
                ng.tags = {
                    **ng.tags,
                    **self.eks_cfg.global_node_tags,
                    **{f"k8s.io/cluster-autoscaler/node-template/label/{k}": v for k, v in ng.labels.items()},
                }
            self.provision_unmanaged_nodegroup(name, ng, max_nodegroup_azs)

        self.install_calico()

    def provision_eks_cluster(self):
        eks_sg = ec2.SecurityGroup(
            self,
            "EKSSG",
            vpc=self.vpc,
            security_group_name=f"{self.name}-EKSSG",
            allow_all_outbound=False,
        )

        # Note: We can't tag the EKS cluster via CDK/CF: https://github.com/aws/aws-cdk/issues/4995
        self.cluster = eks.Cluster(
            self,
            "eks",
            cluster_name=self.name,
            vpc=self.vpc,
            endpoint_access=eks.EndpointAccess.PRIVATE if self.eks_cfg.private_api else None,
            vpc_subnets=[ec2.SubnetType.PRIVATE],
            version=self.eks_version,
            default_capacity=0,
            security_group=eks_sg,
        )

        if self.bastion_sg:
            self.cluster.cluster_security_group.add_ingress_rule(
                peer=self.bastion_sg,
                connection=ec2.Port(
                    protocol=ec2.Protocol("TCP"),
                    string_representation="API Access",
                    from_port=443,
                    to_port=443,
                ),
            )

        cdk.CfnOutput(self, "eks_cluster_name", value=self.cluster.cluster_name)
        cdk.CfnOutput(
            self,
            "eks_kubeconfig_cmd",
            value=f"aws eks update-kubeconfig --name {self.cluster.cluster_name} --region {self.region} --role-arn {self.cluster.kubectl_role.role_arn}",
        )

    def provision_eks_iam_policies(self, s3_policy: iam.ManagedPolicy, r53_zone_ids: List[str]):
        asg_group_statement = iam.PolicyStatement(
            actions=[
                "autoscaling:DescribeAutoScalingInstances",
                "autoscaling:SetDesiredCapacity",
                "autoscaling:TerminateInstanceInAutoScalingGroup",
            ],
            resources=["*"],
            conditions={"StringEquals": {"autoscaling:ResourceTag/eks:cluster-name": self.cluster.cluster_name}},
        )

        self.autoscaler_policy = iam.ManagedPolicy(
            self,
            "autoscaler",
            managed_policy_name=f"{self.name}-autoscaler",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "autoscaling:DescribeAutoScalingGroups",
                        "autoscaling:DescribeLaunchConfigurations",
                        "autoscaling:DescribeTags",
                        "ec2:DescribeLaunchTemplateVersions",
                    ],
                    resources=["*"],
                ),
                asg_group_statement,
            ],
        )

        if r53_zone_ids:
            self.route53_policy = iam.ManagedPolicy(
                self,
                "route53",
                managed_policy_name=f"{self.name}-route53",
                statements=[
                    iam.PolicyStatement(
                        actions=["route53:ListHostedZones"],
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "route53:ChangeResourceRecordSets",
                            "route53:ListResourceRecordSets",
                        ],
                        resources=[f"arn:aws:route53:::hostedzone/{zone_id}" for zone_id in r53_zone_ids],
                    ),
                ],
            )
            cdk.CfnOutput(
                self,
                "route53-zone-id-output",
                value=str(r53_zone_ids),
            )
            self.outputs["route53-txt-owner-id"] = cdk.CfnOutput(
                self,
                "route53-txt-owner-id",
                value=f"{self.name}CDK",
            )

        self.ecr_policy = iam.ManagedPolicy(
            self,
            "DominoEcrReadOnly",
            managed_policy_name=f"{self.name}-DominoEcrRestricted",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=["ecr:*"],
                    conditions={"StringNotEqualsIfExists": {"ecr:ResourceTag/domino-deploy-id": self.name}},
                    resources=[f"arn:aws:ecr:*:{self.account}:*"],
                ),
            ],
        )

        managed_policies = [
            s3_policy,
            self.ecr_policy,
            self.autoscaler_policy,
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEKSWorkerNodePolicy'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEC2ContainerRegistryReadOnly'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEKS_CNI_Policy'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
        ]
        if r53_zone_ids:
            managed_policies.append(self.route53_policy)

        self.ng_role = iam.Role(
            self,
            f'{self.name}-NG',
            role_name=f"{self.name}-NG",
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=managed_policies,
        )

    def _get_machine_image(self, cfg_name: str, image: MachineImage) -> Tuple[Optional[str], Optional[str]]:
        if image:
            return image.ami_id, image.user_data
        return None, None

    def _handle_user_data(
        self, name: str, custom_ami: bool, ssm_agent: bool, user_data_list: List[Union[ec2.UserData, str]]
    ) -> Optional[ec2.UserData]:
        mime_user_data = ec2.MultipartUserData()

        # If we are using default EKS image, tweak kubelet
        if not custom_ami:
            mime_user_data.add_part(
                ec2.MultipartBody.from_user_data(
                    ec2.UserData.custom(
                        'KUBELET_CONFIG=/etc/kubernetes/kubelet/kubelet-config.json\n'
                        'echo "$(jq \'.eventRecordQPS=0\' $KUBELET_CONFIG)" > $KUBELET_CONFIG'
                    )
                ),
            )
            # if not custom AMI, we can install ssm agent. If requested.
            if ssm_agent:
                mime_user_data.add_part(
                    ec2.MultipartBody.from_user_data(
                        ec2.UserData.custom(
                            "yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm",
                        )
                    ),
                )
        for ud in user_data_list:
            if isinstance(ud, str):
                mime_user_data.add_part(
                    ec2.MultipartBody.from_user_data(
                        ec2.UserData.custom(
                            cdk.Fn.sub(
                                ud,
                                {
                                    "NodegroupName": name,
                                    "StackName": self.name,
                                    "ClusterName": self.cluster.cluster_name,
                                },
                            ),
                        ),
                    ),
                )
            if isinstance(ud, ec2.UserData):
                mime_user_data.add_part(ec2.MultipartBody.from_user_data(ud))

        return mime_user_data

    def provision_managed_nodegroup(self, name: str, ng: Type[EKS.NodegroupBase], max_nodegroup_azs: int) -> None:
        ami_id, user_data = self._get_machine_image(name, ng.machine_image)
        machine_image: Optional[ec2.IMachineImage] = (
            ec2.MachineImage.generic_linux({self.region: ami_id}) if ami_id else None
        )
        mime_user_data: Optional[ec2.UserData] = self._handle_user_data(name, ami_id, ng.ssm_agent, [user_data])

        lt = ec2.LaunchTemplate(
            self.cluster,
            f"LaunchTemplate{name}",
            key_name=ng.key_name,
            launch_template_name=f"{self.name}-{name}",
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        ng.disk_size,
                        volume_type=ec2.EbsDeviceVolumeType.GP2,
                    ),
                )
            ],
            machine_image=machine_image,
            user_data=mime_user_data,
        )
        lts = eks.LaunchTemplateSpec(id=lt.launch_template_id, version=lt.version_number)

        for i, az in enumerate(self.vpc.availability_zones[:max_nodegroup_azs]):
            self.cluster.add_nodegroup_capacity(
                f"{self.name}-{name}-{i}",
                nodegroup_name=f"{self.name}-{name}-{az}",
                capacity_type=eks.CapacityType.SPOT if ng.spot else eks.CapacityType.ON_DEMAND,
                min_size=ng.min_size,
                max_size=ng.max_size,
                desired_size=ng.desired_size,
                subnets=ec2.SubnetSelection(
                    subnet_group_name=self.private_subnet_name,
                    availability_zones=[az],
                ),
                instance_types=[ec2.InstanceType(it) for it in ng.instance_types],
                launch_template_spec=lts,
                labels=ng.labels,
                tags=ng.tags,
                node_role=self.ng_role,
            )

    def provision_unmanaged_nodegroup(self, name: str, ng: Type[EKS.NodegroupBase], max_nodegroup_azs: int) -> None:
        ami_id, user_data = self._get_machine_image(name, ng.machine_image)

        machine_image = (
            ec2.MachineImage.generic_linux({self.region: ami_id})
            if ami_id
            else eks.EksOptimizedImage(
                cpu_arch=eks.CpuArch.X86_64,
                kubernetes_version=self.eks_version.version,
                node_type=eks.NodeType.GPU if ng.gpu else eks.NodeType.STANDARD,
            )
        )

        if not hasattr(self, "unmanaged_sg"):
            self.unmanaged_sg = ec2.SecurityGroup(
                self,
                "UnmanagedSG",
                vpc=self.vpc,
                security_group_name=f"{self.name}-sharedNodeSG",
                allow_all_outbound=False,
            )

        if self.bastion_sg:
            self.unmanaged_sg.add_ingress_rule(
                peer=self.bastion_sg,
                connection=ec2.Port(
                    protocol=ec2.Protocol("TCP"),
                    string_representation="ssh",
                    from_port=22,
                    to_port=22,
                ),
            )

        scope = cdk.Construct(self, f"UnmanagedNodeGroup{name}")
        cfn_lt = None
        for i, az in enumerate(self.vpc.availability_zones[:max_nodegroup_azs]):
            indexed_name = f"{self.name}-{name}-{az}"
            asg = aws_autoscaling.AutoScalingGroup(
                scope,
                f"{self.name}-{name}-{i}",
                auto_scaling_group_name=indexed_name,
                instance_type=ec2.InstanceType(ng.instance_types[0]),
                machine_image=machine_image,
                vpc=self.cluster.vpc,
                min_capacity=ng.min_size,
                max_capacity=ng.max_size,
                vpc_subnets=ec2.SubnetSelection(
                    subnet_group_name=self.private_subnet_name,
                    availability_zones=[az],
                ),
                role=self.ng_role,
                security_group=self.unmanaged_sg,
            )
            for k, v in (
                {
                    **ng.tags,
                    **{
                        f"k8s.io/cluster-autoscaler/{self.cluster.cluster_name}": "owned",
                        "k8s.io/cluster-autoscaler/enabled": "true",
                        "eks:cluster-name": self.cluster.cluster_name,
                        "Name": indexed_name,
                    },
                }
            ).items():
                cdk.Tags.of(asg).add(str(k), str(v), apply_to_launched_instances=True)

            mime_user_data = self._handle_user_data(name, ami_id, ng.ssm_agent, [asg.user_data, user_data])

            if not cfn_lt:
                lt = ec2.LaunchTemplate(
                    scope,
                    f"LaunchTemplate{i}",
                    launch_template_name=indexed_name,
                    block_devices=[
                        ec2.BlockDevice(
                            device_name="/dev/xvda",
                            volume=ec2.BlockDeviceVolume.ebs(
                                ng.disk_size,
                                volume_type=ec2.EbsDeviceVolumeType.GP2,
                            ),
                        )
                    ],
                    role=self.ng_role,
                    instance_type=ec2.InstanceType(ng.instance_types[0]),
                    key_name=ng.key_name,
                    machine_image=machine_image,
                    user_data=mime_user_data,
                    security_group=self.unmanaged_sg,
                )
                # mimic adding the security group via the ASG during connect_auto_scaling_group_capacity
                lt.connections.add_security_group(self.cluster.cluster_security_group)
                cfn_lt: ec2.CfnLaunchTemplate = lt.node.default_child
                lt_data = ec2.CfnLaunchTemplate.LaunchTemplateDataProperty(
                    **cfn_lt.launch_template_data._values,
                    metadata_options=ec2.CfnLaunchTemplate.MetadataOptionsProperty(
                        http_endpoint="enabled", http_tokens="required", http_put_response_hop_limit=2
                    ),
                )
                cfn_lt.launch_template_data = lt_data

            # https://github.com/aws/aws-cdk/issues/6734
            cfn_asg: aws_autoscaling.CfnAutoScalingGroup = asg.node.default_child
            # Remove the launch config from our stack
            asg.node.try_remove_child("LaunchConfig")
            cfn_asg.launch_configuration_name = None
            # Attach the launch template to the auto scaling group
            cfn_asg.mixed_instances_policy = cfn_asg.MixedInstancesPolicyProperty(
                launch_template=cfn_asg.LaunchTemplateProperty(
                    launch_template_specification=cfn_asg.LaunchTemplateSpecificationProperty(
                        launch_template_id=cfn_lt.ref,
                        version=lt.version_number,
                    ),
                    overrides=[cfn_asg.LaunchTemplateOverridesProperty(instance_type=it) for it in ng.instance_types],
                ),
            )

            options: dict[str, Any] = {
                "bootstrap_enabled": ami_id is None,
            }
            if not ami_id:
                extra_args: list[str] = []
                if labels := ng.labels:
                    extra_args.append(
                        "--node-labels={}".format(",".join(["{}={}".format(k, v) for k, v in labels.items()]))
                    )

                if taints := ng.taints:
                    extra_args.append(
                        "--register-with-taints={}".format(",".join(["{}={}".format(k, v) for k, v in taints.items()]))
                    )
                options["bootstrap_options"] = eks.BootstrapOptions(kubelet_extra_args=" ".join(extra_args))

            self.cluster.connect_auto_scaling_group_capacity(asg, **options)

    def install_calico(self):
        self._install_calico_manifest()

    def _install_calico_manifest(self):
        # This produces an obnoxious diff on every subsequent run
        # Using a helm chart does not, so we should switch to that
        # However, we need to figure out how to get the helm chart
        # accessible by the CDK lambda first. Not clear how to give
        # s3 perms to it programmatically, and while ECR might be
        # an option it also doesn't seem like there's a way to push
        # the chart with existing api calls.
        # Probably need to do some custom lambda thing.
        for manifest in manifests:
            filename = f"{manifest[0]}.yaml"
            if isfile(filename):
                with open(filename) as f:
                    manifest_text = f.read()
            else:
                manifest_text = requests_get(manifest[1]).text
            loaded_manifests = [yaml_safe_load(i) for i in re_split("^---$", manifest_text, flags=MULTILINE) if i]
            crds = eks.KubernetesManifest(
                self,
                "calico-crds",
                cluster=self.cluster,
                manifest=[crd for crd in loaded_manifests if crd["kind"] == "CustomResourceDefinition"],
            )
            non_crds = eks.KubernetesManifest(
                self,
                "calico",
                cluster=self.cluster,
                manifest=[notcrd for notcrd in loaded_manifests if notcrd["kind"] != "CustomResourceDefinition"],
            )
            non_crds.node.add_dependency(crds)

    def _install_calico_lambda(self):
        # WIP
        k8s_lambda = aws_lambda.Function(
            self,
            "k8s_lambda",
            handler="main",
            runtime=aws_lambda.Runtime.PROVIDED,
            layers=[
                KubectlLayer(self, "KubectlLayer"),
                AwsCliLayer(self, "AwsCliLayer"),
            ],
            vpc=self.vpc,
            code=aws_lambda.AssetCode("cni-bundle.zip"),
            timeout=cdk.Duration.seconds(30),
            environment={"cluster_name": self.cluster.cluster_name},
            security_groups=self.cluster.connections.security_groups,
        )
        self.cluster.connections.allow_default_port_from(self.cluster.connections)
        k8s_lambda.add_to_role_policy(self.s3_stack.s3_api_statement)
        # k8s_lambda.add_to_role_policy(iam.PolicyStatement(
        #    actions=["eks:*"],
        #    resources=[self.cluster.cluster_arn],
        # ))
        self.cluster.aws_auth.add_masters_role(k8s_lambda.role)
        # run_calico_lambda.node.add_dependency(k8s_lambda)

        # This got stuck, need to make a response object?
        # run_calico_lambda = core.CustomResource(
        #    self,
        #    "run_calico_lambda",
        #    service_token=k8s_lambda.function_arn,
        # )

        # This just doesn't trigger
        from aws_cdk.aws_stepfunctions_tasks import LambdaInvoke

        LambdaInvoke(
            self,
            "run_calico_lambda",
            lambda_function=k8s_lambda,
            timeout=cdk.Duration.seconds(120),
        )

    # Override default max of 2 AZs, as well as allow configurability
    @property
    def availability_zones(self):
        return self.cfg.availability_zones or [
            cdk.Fn.select(0, cdk.Fn.get_azs(self.env.region)),
            cdk.Fn.select(1, cdk.Fn.get_azs(self.env.region)),
            cdk.Fn.select(2, cdk.Fn.get_azs(self.env.region)),
        ]
