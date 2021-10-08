from typing import Dict, List

import aws_cdk.aws_iam as iam
from aws_cdk import core as cdk
from aws_cdk.aws_s3 import Bucket


class DominoEksIamProvisioner:
    def __init__(
        self,
        scope: cdk.Construct,
    ) -> None:
        self.scope = scope

    def provision(self, stack_name: str, cluster_name: str, r53_zone_ids: List[str], buckets: Dict[str, Bucket]):
        asg_group_statement = iam.PolicyStatement(
            actions=[
                "autoscaling:DescribeAutoScalingInstances",
                "autoscaling:SetDesiredCapacity",
                "autoscaling:TerminateInstanceInAutoScalingGroup",
            ],
            resources=["*"],
            conditions={"StringEquals": {"autoscaling:ResourceTag/eks:cluster-name": cluster_name}},
        )

        autoscaler_policy = iam.ManagedPolicy(
            self.scope,
            "autoscaler",
            managed_policy_name=f"{stack_name}-autoscaler",
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

        snapshot_policy = iam.ManagedPolicy(
            self.scope,
            "snapshot",
            managed_policy_name=f"{stack_name}-snapshot",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "ec2:CreateSnapshot",
                        "ec2:CreateTags",
                        "ec2:DeleteSnapshot",
                        "ec2:DeleteTags",
                        "ec2:DescribeAvailabilityZones",
                        "ec2:DescribeSnapshots",
                        "ec2:DescribeTags",
                    ],
                    resources=["*"],
                ),
            ],
        )

        ecr_policy = iam.ManagedPolicy(
            self.scope,
            f"{stack_name}-DominoEcrRestricted",
            managed_policy_name=f"{stack_name}-DominoEcrRestricted",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=[
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:BatchGetImage",
                        "ecr:GetDownloadUrlForLayer",
                    ],
                    conditions={"StringNotEqualsIfExists": {"ecr:ResourceTag/domino-deploy-id": stack_name}},
                    resources=[
                        cdk.Arn.format(
                            cdk.ArnComponents(region="*", service="ecr", resource="*"), cdk.Stack.of(self.scope)
                        )
                    ],
                ),
            ],
        )

        # https://github.com/kubernetes-sigs/aws-ebs-csi-driver/blob/helm-chart-aws-ebs-csi-driver-2.1.1/docs/example-iam-policy.json
        ebs_policy_document = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ec2:DescribeAvailabilityZones",
                        "ec2:DescribeInstances",
                        "ec2:DescribeSnapshots",
                        "ec2:DescribeTags",
                        "ec2:DescribeVolumes",
                        "ec2:DescribeVolumesModifications",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ec2:CreateSnapshot",
                        "ec2:AttachVolume",
                        "ec2:DetachVolume",
                        "ec2:ModifyVolume",
                    ],
                    resources=["*"],
                    conditions={"StringLike": {f"aws:ResourceTag/kubernetes.io/cluster/{stack_name}": "owned"}},  # We can't use token cluster_name here, but should be the same
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["ec2:CreateTags"],
                    resources=["arn:aws:ec2:*:*:volume/*", "arn:aws:ec2:*:*:snapshot/*"],
                    conditions={"StringEquals": {"ec2:CreateAction": ["CreateVolume", "CreateSnapshot"]}},
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["ec2:DeleteTags"],
                    resources=["arn:aws:ec2:*:*:volume/*", "arn:aws:ec2:*:*:snapshot/*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["ec2:CreateVolume"],
                    resources=["*"],
                    conditions={"StringLike": {"aws:RequestTag/KubernetesCluster": cluster_name}},
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["ec2:DeleteVolume", "ec2:DeleteSnapshot"],
                    resources=["*"],
                    conditions={"StringLike": {"aws:ResourceTag/KubernetesCluster": cluster_name}},
                ),
            ]
        )

        ebs_csi_policy = iam.ManagedPolicy(
            self.scope,
            f"{stack_name}-ebs-csi",
            managed_policy_name=f"{stack_name}-ebs-csi",
            document=ebs_policy_document,
        )

        managed_policies = [
            ecr_policy,
            autoscaler_policy,
            snapshot_policy,
            ebs_csi_policy,
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEKSWorkerNodePolicy'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEC2ContainerRegistryReadOnly'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonEKS_CNI_Policy'),
            iam.ManagedPolicy.from_aws_managed_policy_name('AmazonSSMManagedInstanceCore'),
        ]

        self.scope.untagged_resources["iam"].extend(
            [ecr_policy.managed_policy_arn, autoscaler_policy.managed_policy_arn, snapshot_policy.managed_policy_arn]
        )

        if r53_zone_ids:
            r53_policy = self.provision_r53_policy(stack_name, r53_zone_ids)
            managed_policies.append(r53_policy)
            self.scope.untagged_resources["iam"].append(r53_policy.managed_policy_arn)

        if buckets:
            s3_policy = self.provision_node_s3_iam_policy(stack_name, buckets)
            managed_policies.append(s3_policy)
            self.scope.untagged_resources["iam"].append(s3_policy.managed_policy_arn)

        return iam.Role(
            self.scope,
            f'{stack_name}-NG',
            role_name=f"{stack_name}-NG",
            assumed_by=iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies=managed_policies,
        )

    def provision_r53_policy(self, stack_name: str, r53_zone_ids: List[str]) -> iam.ManagedPolicy:
        return iam.ManagedPolicy(
            self.scope,
            "route53",
            managed_policy_name=f"{stack_name}-route53",
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
                        cdk.Arn.format(
                            cdk.ArnComponents(
                                account="", region="", service="route53", resource=f"hostedzone/{zone_id}"
                            ),
                            cdk.Stack.of(self.scope),
                        )
                        for zone_id in r53_zone_ids
                    ],
                ),
            ],
        )

    def provision_node_s3_iam_policy(self, stack_name: str, buckets: Dict[str, Bucket]) -> iam.ManagedPolicy:
        return iam.ManagedPolicy(
            self.scope,
            "S3",
            managed_policy_name=f"{stack_name}-S3",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "s3:ListBucket",
                        "s3:GetBucketLocation",
                        "s3:ListBucketMultipartUploads",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "s3:PutObject",
                        "s3:GetObject",
                        "s3:DeleteObject",
                        "s3:ListMultipartUploadParts",
                        "s3:AbortMultipartUpload",
                    ],
                    resources=[f"{b.bucket_arn}*" for b in buckets.values()],
                ),
            ],
        )
