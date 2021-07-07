from typing import Any, Dict, List, Optional, Type, Union

import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
from aws_cdk import aws_autoscaling
from aws_cdk import core as cdk

from domino_cdk import config
from domino_cdk.config.util import IngressRule


class DominoEksNodegroupProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
        cluster: eks.Cluster,
        ng_role: iam.Role,
        stack_name: str,
        eks_cfg: config.EKS,
        eks_version: eks.KubernetesVersion,
        vpc: ec2.Vpc,
        private_subnet_name: str,
        bastion_sg: ec2.SecurityGroup,
    ) -> None:
        self.scope = scope
        self.cluster = cluster
        self.ng_role = ng_role
        self.stack_name = stack_name
        self.eks_cfg = eks_cfg
        self.eks_version = eks_version
        self.vpc = vpc
        self.private_subnet_name = private_subnet_name

        max_nodegroup_azs = self.eks_cfg.max_nodegroup_azs

        def provision_nodegroup(nodegroup: Dict[str, config.EKS.NodegroupBase], prov_func):
            for name, ng in nodegroup.items():
                if not ng.ami_id:
                    ng.labels = {**ng.labels, **self.eks_cfg.global_node_labels}
                    ng.tags = {
                        **ng.tags,
                        **self.eks_cfg.global_node_tags,
                        **{f"k8s.io/cluster-autoscaler/node-template/label/{k}": v for k, v in ng.labels.items()},
                    }
                prov_func(name, ng, max_nodegroup_azs)

        self.provision_security_group(bastion_sg, eks_cfg.nodegroup_ingress_ports)
        provision_nodegroup(self.eks_cfg.managed_nodegroups, self.provision_managed_nodegroup)
        provision_nodegroup(self.eks_cfg.unmanaged_nodegroups, self.provision_unmanaged_nodegroup)

    def provision_managed_nodegroup(
        self, name: str, ng: Type[config.EKS.NodegroupBase], max_nodegroup_azs: int
    ) -> None:
        region = cdk.Stack.of(self.scope).region
        machine_image: Optional[ec2.IMachineImage] = (
            ec2.MachineImage.generic_linux({region: ng.ami_id}) if ng.ami_id else None
        )
        mime_user_data: Optional[ec2.UserData] = self._handle_user_data(name, ng.ami_id, ng.ssm_agent, [ng.user_data])

        lt = ec2.LaunchTemplate(
            self.cluster,
            f"LaunchTemplate{name}",
            key_name=ng.key_name,
            launch_template_name=f"{self.stack_name}-{name}",
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",  # TODO: this only works for AL2
                    volume=ec2.BlockDeviceVolume.ebs(
                        ng.disk_size,
                        delete_on_termination=True,
                        encrypted=True,
                        volume_type=ec2.EbsDeviceVolumeType.GP2,
                    ),
                )
            ],
            machine_image=machine_image,
            user_data=mime_user_data,
            security_group=self.nodegroup_sg,
        )
        lts = eks.LaunchTemplateSpec(id=lt.launch_template_id, version=lt.version_number)

        for i, az in enumerate(self.vpc.availability_zones[:max_nodegroup_azs]):
            self.cluster.add_nodegroup_capacity(
                f"{self.stack_name}-{name}-{i}",
                nodegroup_name=f"{self.stack_name}-{name}-{az}",
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

    def provision_unmanaged_nodegroup(
        self, name: str, ng: Type[config.EKS.NodegroupBase], max_nodegroup_azs: int
    ) -> None:
        region = cdk.Stack.of(self.scope).region
        machine_image = (
            ec2.MachineImage.generic_linux({region: ng.ami_id})
            if ng.ami_id
            else eks.EksOptimizedImage(
                cpu_arch=eks.CpuArch.X86_64,
                kubernetes_version=self.eks_version.version,
                node_type=eks.NodeType.GPU if ng.gpu else eks.NodeType.STANDARD,
            )
        )

        scope = cdk.Construct(self.scope, f"UnmanagedNodeGroup{name}")
        cfn_lt = None
        for i, az in enumerate(self.vpc.availability_zones[:max_nodegroup_azs]):
            indexed_name = f"{self.stack_name}-{name}-{az}"
            asg = aws_autoscaling.AutoScalingGroup(
                scope,
                f"{self.stack_name}-{name}-{i}",
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
                security_group=self.nodegroup_sg,
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

            mime_user_data = self._handle_user_data(name, ng.ami_id, ng.ssm_agent, [ng.user_data, asg.user_data])

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
                                delete_on_termination=True,
                                encrypted=True,
                                volume_type=ec2.EbsDeviceVolumeType.GP2,
                            ),
                        )
                    ],
                    role=self.ng_role,
                    instance_type=ec2.InstanceType(ng.instance_types[0]),
                    key_name=ng.key_name,
                    machine_image=machine_image,
                    user_data=mime_user_data,
                    security_group=self.nodegroup_sg,
                )
                # mimic adding the security group via the ASG during connect_auto_scaling_group_capacity
                lt.connections.add_security_group(self.cluster.cluster_security_group)
                cfn_lt: ec2.CfnLaunchTemplate = lt.node.default_child

                http_tokens = "required" if ng.imdsv2_required else "optional"

                lt_data = ec2.CfnLaunchTemplate.LaunchTemplateDataProperty(
                    **cfn_lt.launch_template_data._values,
                    metadata_options=ec2.CfnLaunchTemplate.MetadataOptionsProperty(
                        http_endpoint="enabled", http_tokens=http_tokens, http_put_response_hop_limit=2
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
                "bootstrap_enabled": ng.ami_id is None,
            }
            if not ng.ami_id:
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

    def provision_security_group(self, bastion_sg: ec2.SecurityGroup, ingress_ports: List[IngressRule]):
        self.nodegroup_sg = ec2.SecurityGroup(
            self.scope,
            "UnmanagedSG",
            vpc=self.vpc,
            security_group_name=f"{self.stack_name}-sharedNodeSG",
            allow_all_outbound=False,
        )

        if bastion_sg:
            self.nodegroup_sg.add_ingress_rule(
                peer=self.bastion_sg,
                connection=ec2.Port(
                    protocol=ec2.Protocol("TCP"),
                    string_representation="ssh",
                    from_port=22,
                    to_port=22,
                ),
            )

        if ingress_ports:
            for rule in ingress_ports:
                for ip_cidr in rule.ip_cidrs:
                    self.nodegroup_sg.add_ingress_rule(
                        peer=ec2.Peer.ipv4(ip_cidr),
                        connection=ec2.Port(
                            protocol=ec2.Protocol(rule.protocol),
                            string_representation=rule.name,
                            from_port=rule.from_port,
                            to_port=rule.to_port,
                        ),
                    )

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
                                    "StackName": self.stack_name,
                                    "ClusterName": self.cluster.cluster_name,
                                },
                            ),
                        ),
                    ),
                )
            if isinstance(ud, ec2.UserData):
                mime_user_data.add_part(ec2.MultipartBody.from_user_data(ud))

        return mime_user_data
