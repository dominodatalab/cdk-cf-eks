from os.path import isfile
from re import MULTILINE
from re import split as re_split
from typing import Any, Optional, Tuple

import aws_cdk.aws_backup as backup
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_efs as efs
import aws_cdk.aws_eks as eks
import aws_cdk.aws_events as events
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as aws_lambda
from aws_cdk import aws_autoscaling
from aws_cdk import core as cdk
from aws_cdk.aws_kms import Key
from aws_cdk.aws_s3 import Bucket, BucketEncryption
from aws_cdk.lambda_layer_awscli import AwsCliLayer
from aws_cdk.lambda_layer_kubectl import KubectlLayer
from requests import get as requests_get
from yaml import dump as yaml_dump
from yaml import safe_load as yaml_safe_load

from domino_cdk.config.base import DominoCDKConfig
from domino_cdk.config.util import MachineImage
from domino_cdk.config.vpc import VPC
from domino_cdk.util import DominoCdkUtil

manifests = [
    [
        "calico",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml",
    ]
]


class ExternalCommandException(Exception):
    """Exception running spawned external commands"""


class DominoEksStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, cfg: DominoCDKConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.outputs = {}
        # The code that defines your stack goes here
        self.cfg = cfg
        self.env = kwargs["env"]
        self.name = self.cfg.name
        cdk.CfnOutput(self, "deploy_name", value=self.name)
        cdk.Tags.of(self).add("domino-deploy-id", self.name)
        for k, v in self.cfg.tags.items():
            cdk.Tags.of(self).add(str(k), str(v))

        self.provision_buckets()
        self.provision_vpc(self.cfg.vpc)
        self.provision_eks_cluster()
        self.install_calico()
        self.provision_efs()
        cdk.CfnOutput(self, "agent_config", value=yaml_dump(self.generate_install_config()))

    def provision_buckets(self):
        self.s3_api_statement = s3_bucket_statement = iam.PolicyStatement(
            actions=[
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListMultipartUploadParts",
                "s3:AbortMultipartUpload",
            ]
        )

        self.buckets = {}
        for bucket, attrs in self.cfg.s3.buckets.items():
            use_sse_kms_key = False
            if attrs.sse_kms_key_id:
                use_sse_kms_key = True
                sse_kms_key = Key.from_key_arn(self, f"{bucket}-kms-key", attrs.sse_kms_key_id)

            self.buckets[bucket] = Bucket(
                self,
                bucket,
                bucket_name=f"{self.name}-{bucket}",
                auto_delete_objects=attrs.auto_delete_objects and attrs.removal_policy_destroy,
                removal_policy=cdk.RemovalPolicy.DESTROY if attrs.removal_policy_destroy else cdk.RemovalPolicy.RETAIN,
                enforce_ssl=True,
                bucket_key_enabled=use_sse_kms_key,
                encryption_key=(sse_kms_key if use_sse_kms_key else None),
                encryption=(BucketEncryption.KMS if use_sse_kms_key else BucketEncryption.S3_MANAGED),
            )
            self.buckets[bucket].add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyIncorrectEncryptionHeader",
                    effect=iam.Effect.DENY,
                    principals=[iam.ArnPrincipal("*")],
                    actions=[
                        "s3:PutObject",
                    ],
                    resources=[f"{self.buckets[bucket].bucket_arn}/*"],
                    conditions={
                        "StringNotEquals": {
                            "s3:x-amz-server-side-encryption": "aws:kms" if use_sse_kms_key else "AES256"
                        }
                    },
                )
            )
            self.buckets[bucket].add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyUnEncryptedObjectUploads",
                    effect=iam.Effect.DENY,
                    principals=[iam.ArnPrincipal("*")],
                    actions=[
                        "s3:PutObject",
                    ],
                    resources=[f"{self.buckets[bucket].bucket_arn}/*"],
                    conditions={"Null": {"s3:x-amz-server-side-encryption": "true"}},
                )
            )
            s3_bucket_statement.add_resources(f"{self.buckets[bucket].bucket_arn}*")
            cdk.CfnOutput(self, f"{bucket}-output", value=self.buckets[bucket].bucket_name)

        self.s3_policy = iam.ManagedPolicy(
            self,
            "S3",
            managed_policy_name=f"{self.name}-S3",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "s3:ListBucket",
                        "s3:GetBucketLocation",
                        "s3:ListBucketMultipartUploads",
                    ],
                    resources=["*"],
                ),
                s3_bucket_statement,
            ],
        )

    def provision_vpc(self, vpc: VPC):
        self.public_subnet_name = f"{self.name}-public"
        self.private_subnet_name = f"{self.name}-private"
        if not vpc.create:
            self.vpc = ec2.Vpc.from_lookup("Vpc", vpc_id=vpc.id)
            return

        self.nat_provider = ec2.NatProvider.gateway()
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs=vpc.max_azs,
            cidr=vpc.cidr,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PUBLIC,
                    name=self.public_subnet_name,
                    cidr_mask=24,  # can't use token ids
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PRIVATE,
                    name=self.private_subnet_name,
                    cidr_mask=24,  # can't use token ids
                ),
            ],
            gateway_endpoints={
                "S3": ec2.GatewayVpcEndpointOptions(service=ec2.GatewayVpcEndpointAwsService.S3),
            },
            nat_gateway_provider=self.nat_provider,
        )
        cdk.Tags.of(self.vpc).add("Name", self.name)
        cdk.CfnOutput(self, "vpc-output", value=self.vpc.vpc_cidr_block)

        # ripped off this: https://github.com/aws/aws-cdk/issues/9573
        pod_cidr = ec2.CfnVPCCidrBlock(self, "PodCidr", vpc_id=self.vpc.vpc_id, cidr_block="100.64.0.0/16")
        c = 0
        for az in self.vpc.availability_zones:
            pod_subnet = ec2.PrivateSubnet(
                self,
                # this can't be okay
                f"{self.name}-pod-{c}",  # Can't use parameter/token in this name
                vpc_id=self.vpc.vpc_id,
                availability_zone=az,
                cidr_block=f"100.64.{c}.0/18",
            )

            pod_subnet.add_default_nat_route(
                [gw for gw in self.nat_provider.configured_gateways if gw.az == az][0].gateway_id
            )
            pod_subnet.node.add_dependency(pod_cidr)
            # TODO: need to tag

            c += 64

        for endpoint in [
            "ec2",  # Only these first three have predefined consts
            "sts",
            "ecr.api",
            "autoscaling",
            "ecr.dkr",
        ]:  # TODO: Do we need an s3 interface as well? or just the gateway?
            self.vpc_endpoint = ec2.InterfaceVpcEndpoint(
                self,
                f"{endpoint}-ENDPOINT",
                vpc=self.vpc,
                service=ec2.InterfaceVpcEndpointAwsService(endpoint, port=443),
                # private_dns_enabled=True,
                subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE),
            )

        if vpc.bastion.enabled:
            self.provision_bastion(vpc.bastion)

    def provision_bastion(self, bastion: dict) -> None:
        if bastion.machine_image:
            bastion_machine_image = ec2.MachineImage.generic_linux(
                {self.region: bastion.machine_image.ami_id},
                user_data=ec2.UserData.custom(bastion.machine_image.user_data),
            )
        else:
            if not self.account.isnumeric():  # TODO: Can we get rid of this requirement?
                raise ValueError(
                    "Error loooking up AMI: Must provide explicit AWS account ID to do AMI lookup. Either provide AMI ID or AWS account id"
                )

            bastion_machine_image = ec2.LookupMachineImage(
                name="ubuntu/images/hvm-ssd/ubuntu-bionic-18.04-amd64-server-*", owners=["099720109477"]
            )

        self.bastion_sg = ec2.SecurityGroup(
            self,
            "bastion_sg",
            vpc=self.vpc,
            security_group_name=f"{self.name}-bastion",
        )

        for rule in bastion.ingress_ports:
            for ip_cidr in rule.ip_cidrs:
                self.bastion_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_cidr),
                    connection=ec2.Port(
                        protocol=ec2.Protocol(rule.protocol),
                        string_representation=rule.name,
                        from_port=rule.from_port,
                        to_port=rule.to_port,
                    ),
                )

        bastion = ec2.Instance(
            self,
            "bastion",
            machine_image=bastion_machine_image,
            vpc=self.vpc,
            instance_type=ec2.InstanceType(bastion.instance_type),
            key_name=bastion.key_name,
            security_group=self.bastion_sg,
            vpc_subnets=ec2.SubnetSelection(
                subnet_group_name=self.public_subnet_name,
            ),
        )

        ec2.CfnEIP(
            self,
            "bastion_eip",
            instance_id=bastion.instance_id,
        )

        cdk.CfnOutput(self, "bastion_public_ip", value=bastion.instance_public_ip)

    def provision_eks_cluster(self):
        eks_version = eks.KubernetesVersion.V1_19

        eks_sg = ec2.SecurityGroup(
            self, "EKSSG", vpc=self.vpc, security_group_name=f"{self.name}-EKSSG", allow_all_outbound=False,
        )

        # Note: We can't tag the EKS cluster via CDK/CF: https://github.com/aws/aws-cdk/issues/4995
        self.cluster = eks.Cluster(
            self,
            "eks",
            cluster_name=self.name,
            vpc=self.vpc,
            endpoint_access=eks.EndpointAccess.PRIVATE if self.cfg.eks.private_api else None,
            vpc_subnets=[ec2.SubnetType.PRIVATE],
            version=eks_version,
            default_capacity=0,
            security_group=eks_sg,
        )

        if self.cfg.vpc.bastion.enabled:
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

        self.provision_eks_iam_policies()

        max_nodegroup_azs = self.cfg.eks.max_nodegroup_azs

        for name, ng in self.cfg.eks.managed_nodegroups.items():
            ng.labels = {**ng.labels, **self.cfg.eks.global_node_labels}
            ng.tags = {**ng.tags, **self.cfg.eks.global_node_tags}
            self.provision_managed_nodegroup(name, ng, max_nodegroup_azs)

        for name, ng in self.cfg.eks.unmanaged_nodegroups.items():
            ng.labels = {**ng.labels, **self.cfg.eks.global_node_labels}
            ng.tags = {**ng.tags, **self.cfg.eks.global_node_tags}
            self.provision_unmanaged_nodegroup(name, ng, max_nodegroup_azs, eks_version)

    def provision_eks_iam_policies(self):
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

        if self.cfg.route53.zone_ids:
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
                        resources=[f"arn:aws:route53:::hostedzone/{zone_id}" for zone_id in self.cfg.route53.zone_ids],
                    ),
                ],
            )
            cdk.CfnOutput(
                self,
                "route53-zone-id-output",
                value=str(self.cfg.route53.zone_ids),
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
            self.ecr_policy,
            self.s3_policy,
            self.autoscaler_policy,
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEKSWorkerNodePolicy'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEC2ContainerRegistryReadOnly'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEKS_CNI_Policy'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
        ]
        if self.cfg.route53.zone_ids:
            managed_policies.append(self.route53_policy)

        self.ng_role = iam.Role(
            self,
            f'{self.name}-NG',
            role_name=f"{self.name}-NG",
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=managed_policies,
        )

    def provision_managed_nodegroup(self, name: str, ng: dict, max_nodegroup_azs: int) -> None:
        # managed nodegroups
        ami_id, user_data = self._get_machine_image(name, ng.machine_image)
        machine_image: Optional[ec2.IMachineImage] = None
        if ami_id:
            machine_image = ec2.MachineImage.generic_linux({self.region: ami_id})

        for i, az in enumerate(self.vpc.availability_zones[:max_nodegroup_azs]):
            disk_size = ng.disk_size
            lts: Optional[eks.LaunchTemplateSpec] = None
            if machine_image:
                lt = ec2.LaunchTemplate(
                    self.cluster,
                    f"LaunchTemplate{name}{i}",
                    launch_template_name=f"{self.name}-{name}-{i}",
                    block_devices=[
                        ec2.BlockDevice(
                            device_name="/dev/xvda",
                            volume=ec2.BlockDeviceVolume.ebs(
                                disk_size,
                                volume_type=ec2.EbsDeviceVolumeType.GP2,
                            ),
                        )
                    ],
                    machine_image=machine_image,
                    user_data=ec2.UserData.custom(cdk.Fn.sub(user_data, {"ClusterName": self.cluster.cluster_name})),
                )
                lts = eks.LaunchTemplateSpec(id=lt.launch_template_id, version=lt.version_number)
                disk_size = None

            self.cluster.add_nodegroup_capacity(
                f"{name}-{i}",  # this might be dangerous
                nodegroup_name=f"{self.name}-{name}-{az}",  # this might be dangerous
                capacity_type=eks.CapacityType.SPOT if ng.spot else eks.CapacityType.ON_DEMAND,
                disk_size=disk_size,
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
                remote_access=eks.NodegroupRemoteAccess(ssh_key_name=ng.key_name) if ng.key_name else None,
            )

    def _get_machine_image(self, cfg_name: str, image: MachineImage) -> Tuple[Optional[str], Optional[str]]:
        if not image:
            return None, None

        ami_id = image.ami_id
        user_data = image.user_data

        if ami_id and user_data:
            return ami_id, user_data

        raise ValueError(f"{cfg_name}: ami_id and user_data must both be specified")

    def provision_unmanaged_nodegroup(
        self, name: str, ng: dict, max_nodegroup_azs: int, eks_version: eks.KubernetesVersion
    ) -> None:
        ami_id, user_data = self._get_machine_image(name, ng.machine_image)

        machine_image = (
            ec2.MachineImage.generic_linux({self.region: ami_id}, user_data=ec2.UserData.custom(user_data))
            if ami_id and user_data
            else eks.EksOptimizedImage(
                cpu_arch=eks.CpuArch.X86_64,
                kubernetes_version=eks_version.version,
                node_type=eks.NodeType.GPU if ng.gpu else eks.NodeType.STANDARD,
            )
        )

        if not hasattr(self, "unmanaged_sg"):
            self.unmanaged_sg = ec2.SecurityGroup(
                self, "UnmanagedSG", vpc=self.vpc, security_group_name=f"{self.name}-sharedNodeSG", allow_all_outbound=False,
            )

        if self.cfg.vpc.bastion.enabled:
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
        for i, az in enumerate(self.vpc.availability_zones[:max_nodegroup_azs]):

            indexed_name = f"{self.name}-{name}-{i}"
            asg = aws_autoscaling.AutoScalingGroup(
                scope,
                f"ASG{i}",
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
                user_data=asg.user_data,
                security_group=self.unmanaged_sg,
            )
            # mimic adding the security group via the ASG during connect_auto_scaling_group_capacity
            lt.connections.add_security_group(self.cluster.cluster_security_group)

            # https://github.com/aws/aws-cdk/issues/6734
            cfn_asg: aws_autoscaling.CfnAutoScalingGroup = asg.node.default_child
            # Remove the launch config from our stack
            asg.node.try_remove_child("LaunchConfig")
            cfn_asg.launch_configuration_name = None
            # Attach the launch template to the auto scaling group
            cfn_lt: ec2.CfnLaunchTemplate = lt.node.default_child
            lt_data = ec2.CfnLaunchTemplate.LaunchTemplateDataProperty(
                **cfn_lt.launch_template_data._values,
                metadata_options=ec2.CfnLaunchTemplate.MetadataOptionsProperty(
                    http_endpoint="enabled", http_tokens="required", http_put_response_hop_limit=2
                ),
            )
            cfn_lt.launch_template_data = lt_data
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
                "bootstrap_enabled": user_data is None,
            }
            if not user_data:
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

                if ng.ssm_agent:
                    # We can only access this as an attribute of either the launch template or asg (both are the
                    # same object)as we are getting it from the default user_data included in the standard EKS ami
                    lt.user_data.add_on_exit_commands(
                        "yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm"
                    )
            elif ng.ssm_agent or ng.labels or ng.taints:
                raise ValueError(
                    "ssm_agent, labels and taints will not be automatically confiugured when user_data is specified in the config. Please set this up accordingly in your user_data."
                )

            self.cluster.connect_auto_scaling_group_capacity(asg, **options)

    def provision_efs(self):
        self.efs = efs.FileSystem(
            self,
            "Efs",
            vpc=self.vpc,
            # encrypted=True,
            file_system_name=self.name,
            # kms_key,
            # lifecycle_policy,
            performance_mode=efs.PerformanceMode.MAX_IO,
            provisioned_throughput_per_second=cdk.Size.mebibytes(100),  # TODO: dev/nondev sizing
            removal_policy=cdk.RemovalPolicy.DESTROY
            if self.cfg.efs.removal_policy_destroy
            else cdk.RemovalPolicy.RETAIN,
            security_group=self.cluster.cluster_security_group,
            throughput_mode=efs.ThroughputMode.PROVISIONED,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE),
        )

        self.efs_access_point = self.efs.add_access_point(
            "access_point",
            create_acl=efs.Acl(
                owner_uid="0",
                owner_gid="0",
                permissions="777",
            ),
            path="/domino",
            posix_user=efs.PosixUser(
                uid="0",
                gid="0",
                # secondary_gids
            ),
        )

        efs_backup = self.cfg.efs.backup
        if efs_backup.enable:
            vault = backup.BackupVault(
                self,
                "efs_backup",
                backup_vault_name=f'{self.name}-efs',
                removal_policy=cdk.RemovalPolicy[efs_backup.removal_policy or cdk.RemovalPolicy.RETAIN.value],
            )
            cdk.CfnOutput(self, "backup-vault", value=vault.backup_vault_name)
            plan = backup.BackupPlan(
                self,
                "efs_backup_plan",
                backup_plan_name=f"{self.name}-efs",
                backup_plan_rules=[
                    backup.BackupPlanRule(
                        backup_vault=vault,
                        delete_after=cdk.Duration.days(d) if (d := efs_backup.delete_after) else None,
                        move_to_cold_storage_after=cdk.Duration.days(d)
                        if (d := efs_backup.move_to_cold_storage_after)
                        else None,
                        rule_name="efs-rule",
                        schedule_expression=events.Schedule.expression(f"cron({efs_backup.schedule})"),
                        start_window=cdk.Duration.hours(1),
                        completion_window=cdk.Duration.hours(3),
                    )
                ],
            )
            backupRole = iam.Role(
                self,
                "efs_backup_role",
                assumed_by=iam.ServicePrincipal("backup.amazonaws.com"),
                role_name=f"{self.name}-efs-backup",
            )
            backup.BackupSelection(
                self,
                "efs_backup_selection",
                backup_plan=plan,
                resources=[backup.BackupResource.from_efs_file_system(self.efs)],
                allow_restores=False,
                backup_selection_name=f"{self.name}-efs",
                role=backupRole,
            )

        self.outputs["efs"] = cdk.CfnOutput(
            self,
            "efs-output",
            value=f"{self.efs.file_system_id}::{self.efs_access_point.access_point_id}",
        )

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
        k8s_lambda.add_to_role_policy(self.s3_api_statement)
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

    def generate_install_config(self):
        agent_cfg = {
            "name": self.name,
            "pod_cidr": self.vpc.vpc_cidr_block,
            "global_node_selectors": self.cfg.eks.global_node_labels,
            "storage_classes": {
                "shared": {
                    "efs": {
                        "region": self.cfg.aws_region,
                        "filesystem_id": self.outputs["efs"].value,
                    }
                },
            },
            "blob_storage": {
                "projects": {
                    "s3": {
                        "region": self.cfg.aws_region,
                        "bucket": self.buckets["blobs"].bucket_name,
                    },
                },
                "logs": {
                    "s3": {
                        "region": self.cfg.aws_region,
                        "bucket": self.buckets["logs"].bucket_name,
                    },
                },
                "backups": {
                    "s3": {
                        "region": self.cfg.aws_region,
                        "bucket": self.buckets["backups"].bucket_name,
                    },
                },
                "default": {
                    "s3": {
                        "region": self.cfg.aws_region,
                        "bucket": self.buckets["blobs"].bucket_name,
                    },
                },
            },
            "autoscaler": {
                "enabled": True,
                "auto_discovery": {
                    "cluster_name": self.cluster.cluster_name,
                },
                "groups": [],
                "aws": {
                    "region": self.cfg.aws_region,
                },
            },
            "internal_docker_registry": {
                "s3_override": {
                    "region": self.cfg.aws_region,
                    "bucket": self.buckets["registry"].bucket_name,
                }
            },
            "services": {
                "nginx_ingress": {},
                "nucleus": {
                    "chart_values": {
                        "keycloak": {
                            "createIntegrationTestUser": True,
                        }
                    }
                },
                "forge": {
                    "chart_values": {
                        "config": {
                            "fullPrivilege": True,
                        },
                    }
                },
            },
        }

        if self.cfg.route53.zone_ids:
            agent_cfg["external_dns"] = {
                "enabled": True,
                "zone_id_filters": self.cfg.route53.zone_ids,
                "txt_owner_id": self.outputs["route53-txt-owner-id"].value,
            }

        agent_cfg["services"]["nginx_ingress"]["chart_values"] = {
            "controller": {
                "kind": "Deployment",
                "hostNetwork": False,
                "config": {"use-proxy-protocol": "true"},
                "service": {
                    "enabled": True,
                    "type": "LoadBalancer",
                    "annotations": {
                        "service.beta.kubernetes.io/aws-load-balancer-internal": False,
                        "service.beta.kubernetes.io/aws-load-balancer-backend-protocol": "tcp",
                        "service.beta.kubernetes.io/aws-load-balancer-ssl-ports": "443",
                        "service.beta.kubernetes.io/aws-load-balancer-connection-idle-timeout": "3600",  # noqa
                        "service.beta.kubernetes.io/aws-load-balancer-proxy-protocol": "*",
                        # "service.beta.kubernetes.io/aws-load-balancer-security-groups":
                        #     "could-propagate-this-instead-of-create"
                    },
                    "targetPorts": {"http": "http", "https": "http"},
                    "loadBalancerSourceRanges": ["0.0.0.0/0"],  # TODO AF
                },
            }
        }

        return DominoCdkUtil.deep_merge(agent_cfg, self.cfg.install)
