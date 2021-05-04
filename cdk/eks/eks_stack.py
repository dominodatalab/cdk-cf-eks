from os.path import isfile
from re import MULTILINE
from re import split as re_split
from typing import Any

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
from yaml import safe_load as yaml_safe_load

manifests = [
    [
        "calico",
        "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml",
    ]
]


class EksStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here
        self.config = self.node.try_get_context("config")
        self.env = kwargs["env"]
        self._name = cdk.CfnParameter(
            self,
            "name",
            type="String",
            description="Unique deployment id",
            default=self.config["name"],
        ).value_as_string
        cdk.CfnOutput(self, "deploy_name", value=self._name)
        cdk.Tags.of(self).add("domino-deploy-id", self.config["name"])
        for k, v in self.config["tags"].items():
            cdk.Tags.of(self).add(str(k), str(v))

        self.provision_buckets()
        self.provision_vpc(self.config["vpc"])
        self.provision_eks_cluster()
        self.install_calico()
        self.provision_efs()

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
                bucket_name=f"{self._name}-{bucket}",
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
            managed_policy_name=f"{self._name}-S3",
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
        self.public_subnet_name = f"{self.config['name']}-public"
        self.private_subnet_name = f"{self.config['name']}-private"
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
        cdk.Tags.of(self.vpc).add("Name", self._name)
        cdk.CfnOutput(self, "vpc-output", value=self.vpc.vpc_cidr_block)

        # ripped off this: https://github.com/aws/aws-cdk/issues/9573
        pod_cidr = ec2.CfnVPCCidrBlock(self, "PodCidr", vpc_id=self.vpc.vpc_id, cidr_block="100.64.0.0/16")
        c = 0
        for az in self.vpc.availability_zones:
            pod_subnet = ec2.PrivateSubnet(
                self,
                # this can't be okay
                f"{self.config['name']}-pod-{c}",  # Can't use parameter/token in this name
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

    def provision_eks_cluster(self):
        eks_version = eks.KubernetesVersion.V1_19
        self.cluster = eks.Cluster(
            self,
            "eks",
            # cluster_name=self._name,  # TODO: Naming this causes mysterious IAM errors, may be related to the weird fleetcommand thing?
            vpc=self.vpc,
            vpc_subnets=[ec2.SubnetType.PRIVATE] if self.config["eks"]["private_api"] else None,
            version=eks_version,
            default_capacity=0,
        )

        cdk.CfnOutput(self, "eks-output", value=self.cluster.cluster_name)

        self.asg_group_statement = iam.PolicyStatement(
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
            managed_policy_name=f"{self._name}-autoscaler",
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
                self.asg_group_statement,
            ],
        )

        if self.config["route53"]["zone_ids"]:
            self.route53_policy = iam.ManagedPolicy(
                self,
                "route53",
                managed_policy_name=f"{self._name}-route53",
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
            cdk.CfnOutput(
                self,
                "route53-txt-owner-id",
                value=f"{self.config['name']}AWS",
            )

        # managed nodegroups
        for name, cfg in self.config["eks"]["managed_nodegroups"].items():
            for i, az in enumerate(self.vpc.availability_zones):
                ng = self.cluster.add_nodegroup_capacity(
                    f"{name}-{i}",  # this might be dangerous
                    nodegroup_name=f"{self._name}-{name}-{az}",  # this might be dangerous
                    capacity_type=eks.CapacityType.SPOT if cfg["spot"] else eks.CapacityType.ON_DEMAND,
                    disk_size=cfg.get("disk_size", None),
                    min_size=cfg["min_size"],
                    max_size=cfg["max_size"],
                    desired_size=cfg["desired_size"],
                    subnets=ec2.SubnetSelection(
                        subnet_group_name=self.private_subnet_name,
                        availability_zones=[az],
                    ),
                    instance_types=[ec2.InstanceType(it) for it in cfg["instance_types"]],
                    labels=cfg["labels"],
                    tags=cfg["tags"],
                )
                self.s3_policy.attach_to_role(ng.role)
                self.autoscaler_policy.attach_to_role(ng.role)
                if self.config["route53"]["zone_ids"]:
                    self.route53_policy.attach_to_role(ng.role)

        for name, cfg in self.config["eks"]["nodegroups"].items():
            self.provision_unmanaged_nodegroup(name, cfg, eks_version)

    def provision_unmanaged_nodegroup(self, name: str, cfg: dict, eks_version: eks.KubernetesVersion) -> None:
        ami_id = cfg.get("ami_id")
        user_data = cfg.get("user_data")

        if ami_id and user_data:
            machine_image = ec2.MachineImage.generic_linux(
                {self.region: ami_id}, user_data=ec2.UserData.custom(user_data)
            )
        elif ami_id or user_data:
            raise ValueError(f"{name}: ami_id and user_data must both be specified")
        else:
            machine_image = eks.EksOptimizedImage(
                cpu_arch=eks.CpuArch.X86_64,
                kubernetes_version=eks_version.version,
                node_type=eks.NodeType.GPU if cfg.get("gpu", False) else eks.NodeType.STANDARD,
            )

        if not hasattr(self, "unmanaged_sg"):
            self.unmanaged_sg = ec2.SecurityGroup(
                self, "UnmanagedSG", vpc=self.vpc, security_group_name=f"{self._name}-sharedNodeSG"
            )

        managed_policies = [self.s3_policy, self.autoscaler_policy]
        if self.config["route53"]["zone_ids"]:
            managed_policies.append(self.route53_policy)

        scope = cdk.Construct(self, f"UnmanagedNodeGroup{name}")
        machine_config = machine_image.get_image(scope)
        for i, az in enumerate(self.vpc.availability_zones):
            az_name = f"{self._name}-{name}-{i}"
            role = iam.Role(
                scope,
                f"NodeGroup{i}",
                role_name=f"{az_name}NodeGroup",
                assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
                managed_policies=managed_policies,
            )

            lt = ec2.LaunchTemplate(
                scope,
                f"LaunchTemplate{i}",
                launch_template_name=az_name,
                block_devices=[
                    ec2.BlockDevice(
                        device_name="/dev/xvda",
                        volume=ec2.BlockDeviceVolume.ebs(
                            cfg["disk_size"],
                            volume_type=ec2.EbsDeviceVolumeType.GP2,
                        ),
                    )
                ],
                role=role,
                instance_type=ec2.InstanceType(cfg["instance_types"][0]),
                machine_image=machine_image,
                user_data=machine_config.user_data,
                security_group=self.unmanaged_sg,
            )
            # mimic adding the security group via the ASG during connect_auto_scaling_group_capacity
            lt.connections.add_security_group(self.cluster.cluster_security_group)

            asg = aws_autoscaling.AutoScalingGroup(
                scope,
                f"ASG{i}",
                auto_scaling_group_name=az_name,
                instance_type=ec2.InstanceType(cfg["instance_types"][0]),
                machine_image=machine_image,
                vpc=self.cluster.vpc,
                min_capacity=cfg["min_size"],
                max_capacity=cfg["max_size"],
                desired_capacity=cfg.get("desired_size", None),
                vpc_subnets=ec2.SubnetSelection(
                    subnet_group_name=self.private_subnet_name,
                    availability_zones=[az],
                ),
                role=role,
                user_data=lt.user_data,
                security_group=self.unmanaged_sg,
            )
            for k, v in (
                {
                    **cfg["tags"],
                    **{
                        f"k8s.io/cluster-autoscaler/{self.cluster.cluster_name}": "owned",
                        "k8s.io/cluster-autoscaler/enabled": "true",
                        "eks:cluster-name": self.cluster.cluster_name,
                    },
                }
            ).items():
                cdk.Tags.of(asg).add(str(k), str(v), apply_to_launched_instances=True)

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
                        "--node-labels '{}'".format(",".join(["{}={}".format(k, v) for k, v in labels.items()]))
                    )

                if taints := cfg.get("taints"):
                    extra_args.append(
                        "--register-with-taints '{}'".format(
                            ",".join(["{}={}".format(k, v) for k, v in taints.items()])
                        )
                    )
                options["bootstrap_options"] = eks.BootstrapOptions(kubelet_extra_args=" ".join(extra_args))

            self.cluster.connect_auto_scaling_group_capacity(asg, **options)

    def provision_efs(self):
        self.efs = efs.FileSystem(
            self,
            "Efs",
            vpc=self.vpc,
            # encrypted=True,
            file_system_name=self._name,
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
                # backup_vault_name=f"{self._name}-efs-backup",
                removal_policy=cdk.RemovalPolicy[efs_backup.get("removal_policy", cdk.RemovalPolicy.RETAIN.value)],
            )
            plan = backup.BackupPlan(
                self,
                "efs_backup_plan",
                backup_plan_name=f"{self._name}-efs",
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
                role_name=f"{self._name}-efs-backup",
            )
            backup.BackupSelection(
                self,
                "efs_backup_selection",
                backup_plan=plan,
                resources=[backup.BackupResource.from_efs_file_system(self.efs)],
                allow_restores=False,
                backup_selection_name=f"{self._name}-efs",
                role=backupRole,
            )

        cdk.CfnOutput(
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
