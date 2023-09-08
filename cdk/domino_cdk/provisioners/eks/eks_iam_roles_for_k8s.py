from typing import Dict, List

import aws_cdk.aws_eks as eks
import aws_cdk.aws_iam as iam
from aws_cdk import CfnJson, Fn
from aws_cdk.aws_s3 import Bucket
from aws_cdk.region_info import Fact, FactName
from constructs import Construct

# Permission groups

s3_global_access_permissions = [
    "s3:ListBucket",
    "s3:GetBucketLocation",
    "s3:ListBucketMultipartUploads",
]

s3_write_permissions = [
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:ListMultipartUploadParts",
    "s3:AbortMultipartUpload",
]

s3_read_permissions = [
    "s3:GetObject",
]

ecr_write_permisions = [
    "ecr:PutImageTagMutability",
    "ecr:StartImageScan",
    "ecr:ListTagsForResource",
    "ecr:UploadLayerPart",
    "ecr:BatchDeleteImage",
    "ecr:ListImages",
    "ecr:DeleteRepository",
    "ecr:CompleteLayerUpload",
    "ecr:TagResource",
    "ecr:DescribeRepositories",
    "ecr:DeleteRepositoryPolicy",
    "ecr:BatchCheckLayerAvailability",
    "ecr:ReplicateImage",
    "ecr:GetLifecyclePolicy",
    "ecr:PutLifecyclePolicy",
    "ecr:DescribeImageScanFindings",
    "ecr:GetLifecyclePolicyPreview",
    "ecr:CreateRepository",
    "ecr:PutImageScanningConfiguration",
    "ecr:GetDownloadUrlForLayer",
    "ecr:DeleteLifecyclePolicy",
    "ecr:PutImage",
    "ecr:UntagResource",
    "ecr:BatchGetImage",
    "ecr:DescribeImages",
    "ecr:StartLifecyclePolicyPreview",
    "ecr:InitiateLayerUpload",
    "ecr:GetRepositoryPolicy",
]

# The bucket policies are auto-generated from the bucket list with the names write-name, read-name. E.g. write_blobs

# Roles. The roles are the collection of the policies.
roles = {
    # E.g. nucleus needs this role
    "blobs-write--logs-read": {
        "blobs": "write",
        "logs": "read",
    },
    # E.g. executor needs this role
    "blobs-write": {"blobs": "write"},
    # E.g. builder needs this role
    "images-write": {"ecr": "write"},
}


class DominoEksK8sIamRolesProvisioner:
    def __init__(
        self,
        scope: Construct,
    ) -> None:
        self.scope = scope

    def provision(self, stack_name: str, cluster: eks.Cluster, buckets: Dict[str, Bucket]):
        # Create dummy service account just to make EKS to do heavy listing of creating OIDC
        # TODO: perform associate_iam_oidc_provider by lambda so we do  not create dummy stuff
        sa = eks.ServiceAccount(cluster, "dummy", cluster=cluster, name="dummy")
        # Then we copy policy doc
        statement_json = sa.role.assume_role_policy.to_json()['Statement'][0]
        del statement_json['Condition']['StringEquals']
        logical_id = self.scope.get_logical_id(
            # Warning! Magic! We go two levels deep because child OpenIdConnectProvider is type Construct but
            # logical_id belongs to type CfnElement, which is linked from below like this.
            cluster.node.find_child("OpenIdConnectProvider").node.default_child.node.default_child
        )
        fn = Fn.select(
            1,
            Fn.split(
                ":oidc-provider/",
                Fn.ref(logical_id),
            ),
        )
        statement_json['Condition']['StringLike'] = CfnJson(
            self.scope, "OidcJson", value={f"{fn}:aud": "sts.amazonaws.com", f"{fn}:sub": "system:serviceaccount:*"}
        )
        managed_policies = {}
        managed_policies["ecr"] = {"write": self.create_ecr_policy(stack_name, "ecr-write", ecr_write_permisions)}

        managed_policies.update(self.create_s3_policies(stack_name, buckets))

        self.scope.untagged_resources["iam"].extend(
            [policy.managed_policy_arn for category in managed_policies.values() for policy in category.values()]
        )

        for name, policy_ref in roles.items():
            iam_role = iam.Role(
                self.scope,
                f"{stack_name}-4SA-{name}",
                # Undesired side effect of this: additional statement is created to trust this principal.
                # Because Role constructor mandates principal and creates assume_role_policy
                # with this statement. And later we cannot neither replace assume_role_policy nor remove this statement.
                # Potentially we can avoid this by using CnfRole but no examples exist. A guesswork can take a week.
                assumed_by=iam.ServicePrincipal('eks.amazonaws.com'),
                role_name=f"{stack_name}-4SA-{name}",
            )
            iam_role.assume_role_policy.add_statements(iam.PolicyStatement.from_json(statement_json))
            for policy_group, policy_mode in policy_ref.items():
                iam_role.add_managed_policy(managed_policies[policy_group][policy_mode])

    def create_ecr_policy(self, stack_name: str, policy_name: str, actions: List[str]):
        partition = Fact.require_fact(self.scope.region, FactName.PARTITION)
        external_policy_name = f"{stack_name}-ECR-{policy_name}"
        return iam.ManagedPolicy(
            self.scope,
            external_policy_name,
            managed_policy_name=external_policy_name,
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=actions,
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=["ecr:*"],
                    conditions={"StringNotEqualsIfExists": {"ecr:ResourceTag/domino-deploy-id": stack_name}},
                    resources=[f"arn:{partition}:ecr:*:{self.scope.account}:*"],
                ),
            ],
        )

    def create_s3_policies(self, stack_name: str, buckets: Dict[str, Bucket]) -> Dict[str, iam.ManagedPolicy]:
        policies = {}
        for bucket_name, bucket in buckets.items():
            if bucket_name not in policies:
                policies[bucket_name] = {}
            # Read
            external_policy_name = f"{stack_name}-S3-{bucket_name}-read"
            policies[bucket_name]["read"] = iam.ManagedPolicy(
                self.scope,
                external_policy_name,
                managed_policy_name=external_policy_name,
                statements=[
                    iam.PolicyStatement(
                        actions=s3_global_access_permissions,
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=s3_read_permissions,
                        resources=[f"{bucket.bucket_arn}*"],
                    ),
                ],
            )
            # Write
            external_policy_name = f"{stack_name}-S3-{bucket_name}-write"
            policies[bucket_name]["write"] = iam.ManagedPolicy(
                self.scope,
                external_policy_name,
                managed_policy_name=external_policy_name,
                statements=[
                    iam.PolicyStatement(
                        actions=s3_global_access_permissions,
                        resources=["*"],
                    ),
                    iam.PolicyStatement(
                        actions=s3_write_permissions,
                        resources=[f"{bucket.bucket_arn}*"],
                    ),
                ],
            )
        return policies
