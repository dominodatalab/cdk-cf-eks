from filecmp import cmp
from glob import glob
from json import loads as json_loads
from os.path import basename, dirname, isfile
from os.path import join as path_join
from re import MULTILINE
from re import split as re_split
from subprocess import run
from time import time
from typing import Any, Dict, Optional, Tuple

import aws_cdk.aws_backup as backup
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecr as ecr
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

manifests = [
    [
        "calico",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml",
    ]
]


class ExternalCommandException(Exception):
    """Exception running spawned external commands"""


class DominoEksStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.outputs = {}
        # The code that defines your stack goes here
        self.config = self.node.try_get_context("config")
        self.env = kwargs["env"]
        self.name = self.config["name"]
        cdk.CfnOutput(self, "deploy_name", value=self.name)
        cdk.Tags.of(self).add("domino-deploy-id", self.name)
        for k, v in self.config["tags"].items():
            cdk.Tags.of(self).add(str(k), str(v))

        self.provision_buckets()
        self.provision_vpc(self.config["vpc"])
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
        for bucket, cfg in self.config["s3"]["buckets"].items():
            use_sse_kms_key = False
            if "sse_kms_key_id" in cfg:
                use_sse_kms_key = True
                sse_kms_key = Key.from_key_arn(self, f"{bucket}-kms-key", cfg["sse_kms_key_id"])

            self.buckets[bucket] = Bucket(
                self,
                bucket,
                bucket_name=f"{self.name}-{bucket}",
                auto_delete_objects=cfg["auto_delete_objects"] and cfg["removal_policy_destroy"],
                removal_policy=cdk.RemovalPolicy.DESTROY if cfg["removal_policy_destroy"] else cdk.RemovalPolicy.RETAIN,
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

    def provision_vpc(self, vpc: dict):
        self.public_subnet_name = f"{self.name}-public"
        self.private_subnet_name = f"{self.name}-private"
        if not vpc["create"]:
            self.vpc = ec2.Vpc.from_lookup("Vpc", vpc_id=vpc["id"])
            return

        self.nat_provider = ec2.NatProvider.gateway()
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs=vpc["max_azs"],
            cidr=vpc["cidr"],
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

        if self.config["vpc"]["bastion"]["enabled"]:
            self.provision_bastion(self.config["vpc"]["bastion"])

    def provision_bastion(self, cfg: dict) -> None:
        ami_id, user_data = self._get_machine_image("bastion", cfg)

        if ami_id:
            bastion_machine_image = ec2.MachineImage.generic_linux(
                {self.region: ami_id}, user_data=ec2.UserData.custom(user_data)
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

        for rule in cfg["ingress_ports"]:
            for ip_cidr in rule["ip_cidrs"]:
                self.bastion_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_cidr),
                    connection=ec2.Port(
                        protocol=ec2.Protocol(rule["protocol"]),
                        string_representation=rule["name"],
                        from_port=rule["from_port"],
                        to_port=rule["to_port"],
                    ),
                )

        bastion = ec2.Instance(
            self,
            "bastion",
            machine_image=bastion_machine_image,
            vpc=self.vpc,
            instance_type=ec2.InstanceType(cfg["instance_type"]),
            key_name=cfg.get("key_name", None),
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
        # Note: We can't tag the EKS cluster via CDK/CF: https://github.com/aws/aws-cdk/issues/4995
        self.cluster = eks.Cluster(
            self,
            "eks",
            cluster_name=self.name,  # TODO: Naming this causes mysterious IAM errors, may be related to the weird fleetcommand thing?
            vpc=self.vpc,
            endpoint_access=eks.EndpointAccess.PRIVATE if self.config["eks"]["private_api"] else None,
            vpc_subnets=[ec2.SubnetType.PRIVATE],
            version=eks_version,
            default_capacity=0,
        )

        cdk.CfnOutput(self, "eks_cluster_name", value=self.cluster.cluster_name)
        cdk.CfnOutput(
            self,
            "eks_kubeconfig_cmd",
            value=f"aws eks update-kubeconfig --name {self.cluster.cluster_name} --region {self.region} --role-arn {self.cluster.kubectl_role.role_arn}",
        )

        self.provision_eks_iam_policies()

        max_nodegroup_azs = self.config["eks"]["max_nodegroup_azs"]

        for name, cfg in self.config["eks"]["managed_nodegroups"].items():
            cfg["labels"] = {**cfg["labels"], **self.config["eks"]["global_node_labels"]}
            self.provision_managed_nodegroup(name, cfg, max_nodegroup_azs)

        for name, cfg in self.config["eks"]["nodegroups"].items():
            cfg["labels"] = {**cfg["labels"], **self.config["eks"]["global_node_labels"]}
            self.provision_unmanaged_nodegroup(name, cfg, max_nodegroup_azs, eks_version)

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

        if self.config["route53"]["zone_ids"]:
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
                        resources=[
                            f"arn:aws:route53:::hostedzone/{zone_id}" for zone_id in self.config["route53"]["zone_ids"]
                        ],
                    ),
                ],
            )
            cdk.CfnOutput(
                self,
                "route53-zone-id-output",
                value=str(self.config["route53"]["zone_ids"]),
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
                    conditions={"StringNotEqualsIfExists": {"ecr:ResourceTag/domino-deploy-id": self.config["name"]}},
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
        if self.config["route53"]["zone_ids"]:
            managed_policies.append(self.route53_policy)

        self.ng_role = iam.Role(
            self,
            f'{self.config["name"]}-NG',
            role_name=f"{self.name}-NG",
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=managed_policies,
        )

    def provision_managed_nodegroup(self, name: str, cfg: dict, max_nodegroup_azs: int) -> None:
        # managed nodegroups
        ami_id, user_data = self._get_machine_image(name, cfg)
        machine_image: Optional[ec2.IMachineImage] = None
        if ami_id:
            machine_image = ec2.MachineImage.generic_linux({self.region: ami_id})

        for i, az in enumerate(self.vpc.availability_zones[:max_nodegroup_azs]):
            disk_size = cfg.get("disk_size", None)
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
                                cfg["disk_size"],
                                volume_type=ec2.EbsDeviceVolumeType.GP2,
                            ),
                        )
                    ],
                    machine_image=machine_image,
                    user_data=ec2.UserData.custom(cdk.Fn.sub(user_data, {"ClusterName": self.cluster.cluster_name})),
                )
                lts = eks.LaunchTemplateSpec(id=lt.launch_template_id, version=lt.version_number)
                disk_size = None

        ng = self.cluster.add_nodegroup_capacity(
            f"{name}-{i}",  # this might be dangerous
            nodegroup_name=f"{self.name}-{name}-{az}",  # this might be dangerous
            capacity_type=eks.CapacityType.SPOT if cfg["spot"] else eks.CapacityType.ON_DEMAND,
            disk_size=disk_size,
            min_size=cfg["min_size"],
            max_size=cfg["max_size"],
            desired_size=cfg["desired_size"],
            subnets=ec2.SubnetSelection(
                subnet_group_name=self.private_subnet_name,
                availability_zones=[az],
            ),
            instance_types=[ec2.InstanceType(it) for it in cfg["instance_types"]],
            launch_template_spec=lts,
            labels=cfg["labels"],
            tags=cfg["tags"],
            node_role=ng_role,
            remote_access=eks.NodegroupRemoteAccess(cfg["key_name"]),
        )

    def _get_machine_image(self, cfg_name: str, cfg: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        image = cfg.get("machine_image", {})

        if not image:
            return None, None

        ami_id = image.get("ami_id")
        user_data = image.get("user_data")

        if ami_id and user_data:
            return ami_id, user_data

        raise ValueError(f"{cfg_name}: ami_id and user_data must both be specified")

    def provision_unmanaged_nodegroup(
        self, name: str, cfg: dict, max_nodegroup_azs: int, eks_version: eks.KubernetesVersion
    ) -> None:
        ami_id, user_data = self._get_machine_image(name, cfg)

        machine_image = (
            ec2.MachineImage.generic_linux({self.region: ami_id}, user_data=ec2.UserData.custom(user_data))
            if ami_id and user_data
            else eks.EksOptimizedImage(
                cpu_arch=eks.CpuArch.X86_64,
                kubernetes_version=eks_version.version,
                node_type=eks.NodeType.GPU if cfg.get("gpu", False) else eks.NodeType.STANDARD,
            )
        )

        if not hasattr(self, "unmanaged_sg"):
            self.unmanaged_sg = ec2.SecurityGroup(
                self, "UnmanagedSG", vpc=self.vpc, security_group_name=f"{self.name}-sharedNodeSG"
            )

        if self.config["vpc"]["bastion"]["enabled"]:
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
                instance_type=ec2.InstanceType(cfg["instance_types"][0]),
                machine_image=machine_image,
                vpc=self.cluster.vpc,
                min_capacity=cfg["min_size"],
                max_capacity=cfg["max_size"],
                vpc_subnets=ec2.SubnetSelection(
                    subnet_group_name=self.private_subnet_name,
                    availability_zones=[az],
                ),
                role=self.ng_role,
                security_group=self.unmanaged_sg,
            )
            for k, v in (
                {
                    **cfg["tags"],
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
                            cfg["disk_size"],
                            volume_type=ec2.EbsDeviceVolumeType.GP2,
                        ),
                    )
                ],
                role=self.ng_role,
                instance_type=ec2.InstanceType(cfg["instance_types"][0]),
                key_name=cfg["key_name"],
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
            cfn_asg.mixed_instances_policy = cfn_asg.MixedInstancesPolicyProperty(
                launch_template=cfn_asg.LaunchTemplateProperty(
                    launch_template_specification=cfn_asg.LaunchTemplateSpecificationProperty(
                        launch_template_id=cfn_lt.ref,
                        version=lt.version_number,
                    ),
                    overrides=[
                        cfn_asg.LaunchTemplateOverridesProperty(instance_type=it) for it in cfg["instance_types"]
                    ],
                ),
            )

            options: dict[str, Any] = {
                "bootstrap_enabled": user_data is None,
            }
            if not user_data:
                extra_args: list[str] = []
                if labels := cfg.get("labels"):
                    extra_args.append(
                        "--node-labels={}".format(",".join(["{}={}".format(k, v) for k, v in labels.items()]))
                    )

                if taints := cfg.get("taints"):
                    extra_args.append(
                        "--register-with-taints={}".format(",".join(["{}={}".format(k, v) for k, v in taints.items()]))
                    )
                options["bootstrap_options"] = eks.BootstrapOptions(kubelet_extra_args=" ".join(extra_args))
                
                if cfg["ssm_agent"]:
                    asg.user_data.add_on_exit_commands("yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm")

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
            if self.config["efs"]["removal_policy_destroy"]
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

        efs_backup = self.config["efs"]["backup"]
        if efs_backup["enable"]:
            vault = backup.BackupVault(
                self,
                "efs_backup",
                backup_vault_name=f'{self.name}-efs',
                removal_policy=cdk.RemovalPolicy[efs_backup.get("removal_policy", cdk.RemovalPolicy.RETAIN.value)],
            )
            cdk.CfnOutput(self, "backup-vault", value=vault.backup_vault_name)
            plan = backup.BackupPlan(
                self,
                "efs_backup_plan",
                backup_plan_name=f"{self.name}-efs",
                backup_plan_rules=[
                    backup.BackupPlanRule(
                        backup_vault=vault,
                        delete_after=cdk.Duration.days(d) if (d := efs_backup.get("delete_after")) else None,
                        move_to_cold_storage_after=cdk.Duration.days(d)
                        if (d := efs_backup.get("move_to_cold_storage_after"))
                        else None,
                        rule_name="efs-rule",
                        schedule_expression=events.Schedule.expression(f"cron({efs_backup['schedule']})"),
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
        return self.config["availability_zones"] or [
            cdk.Fn.select(0, cdk.Fn.get_azs(self.env.region)),
            cdk.Fn.select(1, cdk.Fn.get_azs(self.env.region)),
            cdk.Fn.select(2, cdk.Fn.get_azs(self.env.region)),
        ]

    def generate_install_config(self):
        cfg = {
            "name": self.name,
            "pod_cidr": self.vpc.vpc_cidr_block,
            "global_node_selectors": self.config["eks"]["global_node_labels"],
            "storage_classes": {
                "shared": {
                    "efs": {
                        "region": self.config["aws_region"],
                        "filesystem_id": self.outputs["efs"].value,
                    }
                },
            },
            "blob_storage": {
                "projects": {
                    "s3": {
                        "region": self.config["aws_region"],
                        "bucket": self.buckets["blobs"].bucket_name,
                    },
                },
                "logs": {
                    "s3": {
                        "region": self.config["aws_region"],
                        "bucket": self.buckets["logs"].bucket_name,
                    },
                },
                "backups": {
                    "s3": {
                        "region": self.config["aws_region"],
                        "bucket": self.buckets["backups"].bucket_name,
                    },
                },
                "default": {
                    "s3": {
                        "region": self.config["aws_region"],
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
                    "region": self.config["aws_region"],
                },
            },
            "internal_docker_registry": {
                "s3_override": {
                    "region": self.config["aws_region"],
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

        if self.config["route53"]["zone_ids"]:
            cfg["external_dns"] = {
                "enabled": True,
                "zone_id_filters": self.config["route53"]["zone_ids"],
                "txt_owner_id": self.outputs["route53-txt-owner-id"].value,
            }

        cfg["services"]["nginx_ingress"]["chart_values"] = {
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

        cfg = deep_merge(cfg, self.config["install"])

        return cfg

    @classmethod
    def generate_asset_parameters(cls, asset_dir: str, asset_bucket: str, stack_name: str, manifest_file: str = None):
        with open(manifest_file or path_join(asset_dir, "manifest.json")) as f:
            cfg = json_loads(f.read())['artifacts'][stack_name]['metadata'][f"/{stack_name}"]

        parameters = {}

        for c in cfg:
            if c["type"] == "aws:cdk:asset":
                d = c["data"]
                path = d['path']
                if ".zip" not in path and ".json" not in path and not isfile(path_join(asset_dir, f"path.zip")):
                    shell_command = f"cd {asset_dir}/{path}/ && zip -9r {path}.zip ./* && mv {path}.zip ../"
                    output = run(shell_command, shell=True, capture_output=True)
                    if output.returncode:
                        raise ExternalCommandException(
                            f"Error running: {shell_command}\nretval: {output.returncode}\nstdout: {output.stdout.decode()}\nstderr: {output.stderr.decode()}"
                        )
                    path = f"{path}.zip"
                parameters[d['artifactHashParameter']] = d['sourceHash']
                parameters[d['s3BucketParameter']] = asset_bucket
                parameters[d['s3KeyParameter']] = f"||{path}"

        return parameters

    # disable_random_templates is a negative flag that's False by default to facilitate the naive cli access (ie any parameter given triggers it)
    @classmethod
    def generate_terraform_bootstrap(
        cls,
        module_path: str,
        asset_bucket: str,
        asset_dir: str,
        aws_region: str,
        name: str,
        stack_name: str,
        output_dir: str,
        disable_random_templates: bool = False,
        iam_role_arn: str = "",
    ):
        template_filename = path_join(asset_dir, f"{stack_name}.template.json")

        if not disable_random_templates:
            template_files = sorted(glob(f"{asset_dir}/{stack_name}-*.template.json"))
            last_template_file = template_files[-1] if template_files else None

            # Generate new timestamped template file?
            if not last_template_file or not cmp(template_filename, last_template_file):
                ts_template_filename = f"{stack_name}-{int(time())}.template.json"
                shell_command = f"cp {template_filename} {asset_dir}/{ts_template_filename}"
                output = run(shell_command, shell=True, capture_output=True)
                if output.returncode:
                    raise ExternalCommandException(
                        f"Error running: {shell_command}\nretval: {output.returncode}\nstdout: {output.stdout.decode()}\nstderr: {output.stderr.decode()}"
                    )
                template_filename = ts_template_filename
            else:
                template_filename = last_template_file
        return {
            "module": {
                "cdk": {
                    "source": module_path,
                    "asset_bucket": asset_bucket,
                    "asset_dir": asset_dir,
                    "aws_region": aws_region,
                    "name": name,
                    "iam_role_arn": iam_role_arn,
                    "parameters": cls.generate_asset_parameters(asset_dir, asset_bucket, stack_name),
                    "template_filename": basename(template_filename),
                    "output_dir": output_dir,
                },
            },
            "output": {
                "cloudformation_outputs": {
                    "value": "${module.cdk.cloudformation_outputs}",
                }
            },
        }

    @classmethod
    def config_template(cls):
        with open(path_join(dirname(__file__), "config_template.yaml")) as f:
            return yaml_safe_load(f.read())


def deep_merge(*dictionaries) -> dict:
    """
    Recursive dict merge.

    Takes any number of dictionaries as arguments. Each subsequent dictionary will be overlaid on the previous ones
    before. Therefore, the rightmost dictionary's value will take precedence. None values will be interpreted as
    empty dictionaries, but otherwise arguments provided must be of the dict type.
    """

    def check_type(dx) -> dict:
        if dx is None:
            dx = {}
        if not isinstance(dx, dict):
            raise TypeError("Must provide only dictionaries!")
        return dx

    def merge(alpha, omega, key):
        if isinstance(alpha.get(key), dict) and isinstance(omega[key], dict):
            return deep_merge(alpha[key], omega[key])
        else:
            return omega[key]

    def overlay(alpha: dict, omega: dict) -> dict:
        return {**alpha, **{k: merge(alpha, omega, k) for k, _ in omega.items()}}

    if 0 == len(dictionaries):
        return {}
    base_dict = check_type(dictionaries[0])
    return base_dict if len(dictionaries) == 1 else overlay(base_dict, deep_merge(*dictionaries[1:]))
