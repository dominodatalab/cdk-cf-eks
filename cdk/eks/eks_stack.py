from os.path import isfile
from re import MULTILINE, split as re_split
from requests import get as requests_get
from yaml import safe_load as yaml_safe_load

from aws_cdk.aws_s3 import Bucket, BucketEncryption
from aws_cdk.aws_kms import Key
from aws_cdk import core as cdk
# For consistency with other languages, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.
from aws_cdk import core
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_efs as efs
import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as aws_lambda
from aws_cdk.lambda_layer_kubectl import KubectlLayer
from aws_cdk.lambda_layer_awscli import AwsCliLayer


manifests = [["calico", "https://raw.githubusercontent.com/aws/amazon-vpc-cni-k8s/v1.7.10/config/master/calico.yaml"]]

class EksStack(cdk.Stack):
    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here
        self.config = self.node.try_get_context("config")
        self.vpc = self.config["vpc"]
        self.env = kwargs["env"]
        self.name = self.config["name"]
        self.buckets = {}

        self.s3_api_statement = s3_bucket_statement = iam.PolicyStatement(
            actions=[
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListMultipartUploadParts",
                "s3:AbortMultipartUpload",
            ]
        )
        for bucket, cfg in self.config["s3"]["buckets"].items():

            use_sse_kms_key = False
            if "sse_kms_key_id" in cfg:
                use_sse_kms_key = True
                sse_kms_key = Key.from_key_arn(self, f"{self.name}-{bucket}-kms-key", cfg["sse_kms_key_id"])

            self.buckets[bucket] = Bucket(self, f"{self.name}-{bucket}",
                                          bucket_name=f"{self.name}-{bucket}",
                                          auto_delete_objects=cfg["auto_delete_objects"] and cfg["removal_policy_destroy"],
                                          removal_policy=core.RemovalPolicy.DESTROY if cfg["removal_policy_destroy"] else core.RemovalPolicy.RETAIN,
                                          enforce_ssl=True,
                                          bucket_key_enabled=use_sse_kms_key,
                                          encryption_key=(sse_kms_key if use_sse_kms_key else None),
                                          encryption=(BucketEncryption.KMS if use_sse_kms_key else BucketEncryption.S3_MANAGED)
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
                    }
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
                    conditions={
                        "Null": {
                            "s3:x-amz-server-side-encryption": "true"
                        }
                    }
                )
            )
            s3_bucket_statement.add_resources(f"{self.buckets[bucket].bucket_arn}*")

        s3_policy = iam.Policy(
            self,
            f"{self.name}-S3",
            policy_name=f"{self.name}-S3",
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

        if self.vpc["create"]:
            self.nat_provider = ec2.NatProvider.gateway()
            self.vpc = ec2.Vpc(
                self,
                "VPC",
                max_azs=self.vpc["max_azs"],
                cidr=self.vpc["cidr"],
                subnet_configuration=[
                    ec2.SubnetConfiguration(
                        subnet_type=ec2.SubnetType.PUBLIC, name="Public", cidr_mask=24
                    ),
                    ec2.SubnetConfiguration(
                        subnet_type=ec2.SubnetType.PRIVATE, name="Private", cidr_mask=24
                    ),
                ],
                gateway_endpoints={
                    "S3": ec2.GatewayVpcEndpointOptions(
                        service=ec2.GatewayVpcEndpointAwsService.S3
                    ),
                },
                nat_gateway_provider=self.nat_provider,
            )

            # ripped off this: https://github.com/aws/aws-cdk/issues/9573
            pod_cidr = ec2.CfnVPCCidrBlock(
                self, "PodCidr", vpc_id=self.vpc.vpc_id, cidr_block="100.64.0.0/16"
            )
            c = 0
            for az in self.vpc.availability_zones:
                pod_subnet = ec2.PrivateSubnet(
                    self,
                    f"{self.name}-pod-{c}",  # this can't be okay
                    vpc_id=self.vpc.vpc_id,
                    availability_zone=az,
                    cidr_block=f"100.64.{c}.0/18",
                )

                pod_subnet.add_default_nat_route(
                    [gw for gw in self.nat_provider.configured_gateways if gw.az == az][
                        0
                    ].gateway_id
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
        else:
            self.vpc = ec2.Vpc.from_lookup("Vpc", vpc_id=self.vpc["id"])

        self.cluster = eks.Cluster(
            self,
            "Eks",
            vpc=self.vpc,
            vpc_subnets=[ec2.SubnetType.PRIVATE]
            if self.config["eks"]["private_api"]
            else None,
            version=eks.KubernetesVersion.V1_19,
            default_capacity=0,
        )

        asg_group_statement = iam.PolicyStatement(
            actions=[
                "autoscaling:DescribeAutoScalingInstances",
                "autoscaling:SetDesiredCapacity",
                "autoscaling:TerminateInstanceInAutoScalingGroup",
            ],
        )

        asg_policy = iam.Policy(
            self,
            "ASG",
            policy_name="ASG",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "autoscaling:DescribeAutoScalingGroups",
                        "autoscaling:DescribeLaunchConfigurations",
                        "autoscaling:DescribeTags",
                    ],
                    resources=["*"],
                ),
            ],
        )

        for name, cfg in self.config["eks"]["nodegroups"].items():
            c = 1
            for az in self.vpc.availability_zones:
                ng = self.cluster.add_nodegroup_capacity(
                    f"{name}-{c}",  # this might be dangerous
                    capacity_type=eks.CapacityType.SPOT
                    if cfg["spot"]
                    else eks.CapacityType.ON_DEMAND,
                    disk_size=cfg.get("disk_size", None),
                    min_size=cfg["min"],
                    max_size=cfg["max"],
                    desired_size=cfg["desired"],
                    subnets=ec2.SubnetSelection(
                        subnet_group_name="Private",
                        availability_zones=[az],
                    ),
                    instance_types=[
                        ec2.InstanceType(it) for it in cfg["instance_types"]
                    ],
                    labels=cfg["tags"],
                    tags=cfg["tags"],
                )
                s3_policy.attach_to_role(ng.role)
                asg_group_statement.add_resources(ng.nodegroup_arn)
                asg_policy.attach_to_role(ng.role)
                c += 1

        self.install_calico()

        self.efs = efs.FileSystem(
            self,
            "Efs",
            vpc=self.vpc,
            # enable_automatic_backups=True,
            # encrypted=True,
            file_system_name=self.name,
            # kms_key,
            # lifecycle_policy,
            performance_mode=efs.PerformanceMode.MAX_IO,
            provisioned_throughput_per_second=core.Size.mebibytes(
                100
            ),  # TODO: dev/nondev sizing
            removal_policy=core.RemovalPolicy.DESTROY if self.config["efs"]["removal_policy_destroy"] else core.RemovalPolicy.RETAIN,
            security_group=self.cluster.cluster_security_group,
            throughput_mode=efs.ThroughputMode.PROVISIONED,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE),
        )

        self.efs.add_access_point(
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
            crds = eks.KubernetesManifest(self, "calico-crds", cluster=self.cluster, manifest=[crd for crd in loaded_manifests if crd["kind"] == "CustomResourceDefinition"])
            non_crds = eks.KubernetesManifest(self, "calico", cluster=self.cluster, manifest=[notcrd for notcrd in loaded_manifests if notcrd["kind"] != "CustomResourceDefinition"])
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
            timeout=core.Duration.seconds(30),
            environment={
                "cluster_name": self.cluster.cluster_name
            },
            security_groups=self.cluster.connections.security_groups,
        )
        self.cluster.connections.allow_default_port_from(self.cluster.connections)
        k8s_lambda.add_to_role_policy(self.s3_api_statement)
        #k8s_lambda.add_to_role_policy(iam.PolicyStatement(
        #    actions=["eks:*"],
        #    resources=[self.cluster.cluster_arn],
        #))
        self.cluster.aws_auth.add_masters_role(k8s_lambda.role)
        #run_calico_lambda.node.add_dependency(k8s_lambda)

        # This got stuck, need to make a response object?
        #run_calico_lambda = core.CustomResource(
        #    self,
        #    "run_calico_lambda",
        #    service_token=k8s_lambda.function_arn,
        #)

        # This just doesn't trigger
        from aws_cdk.aws_stepfunctions_tasks import LambdaInvoke
        LambdaInvoke(
            self,
            "run_calico_lambda",
            lambda_function=k8s_lambda,
            timeout=core.Duration.seconds(120),
        )


    # Override default max of 2 AZs, as well as allow configurability
    @property
    def availability_zones(self):
        return self.config["availability_zones"] or [
            core.Fn.select(0, core.Fn.get_azs(self.env.region)),
            core.Fn.select(1, core.Fn.get_azs(self.env.region)),
            core.Fn.select(2, core.Fn.get_azs(self.env.region)),
        ]
