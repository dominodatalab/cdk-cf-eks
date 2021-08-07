from typing import Optional

import aws_cdk.aws_iam as iam
from aws_cdk import core as cdk
from aws_cdk.aws_kms import Key
from aws_cdk.aws_s3 import (
    BlockPublicAccess,
    Bucket,
    BucketAccessControl,
    BucketEncryption,
)
from aws_cdk.region_info import Fact, FactName

from domino_cdk import config


class DominoS3Provisioner:
    def __init__(self, parent: cdk.Construct, construct_id: str, name: str, s3: config.S3, nest: bool, **kwargs):
        self.parent = parent
        self.scope = cdk.NestedStack(self.parent, construct_id, **kwargs) if nest else self.parent
        self.monitoring_bucket: Optional[Bucket] = None
        self.provision_buckets(name, s3)

    def _provision_bucket(
        self,
        stack_name: str,
        bucket_id: str,
        attrs: config.S3.BucketList.Bucket,
        server_access_logs_bucket: Optional[Bucket] = None,
        require_encryption: bool = True,
        **kwargs,
    ) -> Bucket:
        use_sse_kms_key = False
        if attrs.sse_kms_key_id:
            use_sse_kms_key = True
            sse_kms_key = Key.from_key_arn(self.scope, f"{bucket_id}-kms-key", attrs.sse_kms_key_id)

        bucket_name = attrs.name or f"{stack_name}-{bucket_id}"
        bucket = Bucket(
            self.scope,
            bucket_id,
            bucket_name=bucket_name,
            auto_delete_objects=attrs.auto_delete_objects and attrs.removal_policy_destroy,
            removal_policy=cdk.RemovalPolicy.DESTROY if attrs.removal_policy_destroy else cdk.RemovalPolicy.RETAIN,
            enforce_ssl=True,
            bucket_key_enabled=use_sse_kms_key,
            encryption_key=(sse_kms_key if use_sse_kms_key else None),
            encryption=(BucketEncryption.KMS if use_sse_kms_key else BucketEncryption.S3_MANAGED),
            block_public_access=BlockPublicAccess.BLOCK_ALL,
            server_access_logs_prefix=f"{bucket_name}/" if server_access_logs_bucket else None,
            server_access_logs_bucket=server_access_logs_bucket,
            versioned=True,
            **kwargs,
        )

        # though the implicit dependency works well on bucket creation, it isn't respected
        # on destroy so access logs for the destruction may cause a failure to delete all
        # objects in the monitoring bucket
        if server_access_logs_bucket:
            bucket.node.add_dependency(server_access_logs_bucket)

        if require_encryption:
            bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyIncorrectEncryptionHeader",
                    effect=iam.Effect.DENY,
                    principals=[iam.ArnPrincipal("*")],
                    actions=[
                        "s3:PutObject",
                    ],
                    resources=[f"{bucket.bucket_arn}/*"],
                    conditions={
                        "StringNotEquals": {
                            "s3:x-amz-server-side-encryption": "aws:kms" if use_sse_kms_key else "AES256"
                        }
                    },
                )
            )
            bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="DenyUnEncryptedObjectUploads",
                    effect=iam.Effect.DENY,
                    principals=[iam.ArnPrincipal("*")],
                    actions=[
                        "s3:PutObject",
                    ],
                    resources=[f"{bucket.bucket_arn}/*"],
                    conditions={"Null": {"s3:x-amz-server-side-encryption": "true"}},
                )
            )

        return bucket

    def provision_buckets(self, stack_name: str, s3: config.S3):
        if s3.buckets.monitoring:
            self.monitoring_bucket = self._provision_bucket(
                stack_name,
                "monitoring",
                s3.buckets.monitoring,
                access_control=BucketAccessControl.LOG_DELIVERY_WRITE,
                require_encryption=False,
            )

            region = cdk.Stack.of(self.scope).region
            self.monitoring_bucket.grant_put(
                iam.AccountPrincipal(Fact.require_fact(region, FactName.ELBV2_ACCOUNT)), "*"
            )

            self.monitoring_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="AWSLogDeliveryWrite",
                    effect=iam.Effect.ALLOW,
                    principals=[iam.ServicePrincipal("delivery.logs.amazonaws.com")],
                    actions=[
                        "s3:PutObject",
                    ],
                    resources=[f"{self.monitoring_bucket.bucket_arn}/*"],
                    conditions={"StringEquals": {"s3:x-amz-acl": "bucket-owner-full-control"}},
                )
            )

            self.monitoring_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="AWSLogDeliveryCheck",
                    effect=iam.Effect.ALLOW,
                    principals=[iam.ServicePrincipal("delivery.logs.amazonaws.com")],
                    actions=[
                        "s3:GetBucketAcl",
                        "s3:ListBucket",
                    ],
                    resources=[self.monitoring_bucket.bucket_arn],
                )
            )

            cdk.CfnOutput(self.parent, "monitoring-bucket-output", value=self.monitoring_bucket.bucket_name)

        self.buckets = {
            bucket: self._provision_bucket(stack_name, bucket, attrs, server_access_logs_bucket=self.monitoring_bucket)
            for bucket, attrs in vars(s3.buckets).items() if attrs and bucket != "monitoring"  # skipping NoneType bucket is for tests, config prevents loading
        }

        for bucket_id, bucket in self.buckets.items():
            cdk.CfnOutput(self.parent, f"{bucket_id}-bucket-output", value=bucket.bucket_name)
