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
        self.provision_buckets(name, s3)

    def _provision_bucket(
        self,
        stack_name: str,
        bucket_id: str,
        attrs: config.S3.Bucket,
        server_access_logs_bucket: Optional[Bucket] = None,
        **kwargs,
    ) -> Bucket:
        use_sse_kms_key = False
        if attrs.sse_kms_key_id:
            use_sse_kms_key = True
            # TODO: is this correct???
            sse_kms_key = Key.from_key_arn(self.scope, f"{bucket_id}-kms-key", attrs.sse_kms_key_id)

        bucket_name = f"{stack_name}-{bucket_id}"
        bucket = Bucket(
            self.scope,
            bucket_id,
            bucket_name=bucket_name,
            auto_delete_objects=attrs.auto_delete_objects and attrs.removal_policy_destroy,
            removal_policy=cdk.RemovalPolicy.DESTROY if attrs.removal_policy_destroy else cdk.RemovalPolicy.RETAIN,
            enforce_ssl=True,  # attrs.require_encryption,
            bucket_key_enabled=use_sse_kms_key,
            encryption_key=(sse_kms_key if use_sse_kms_key else None),
            encryption=(BucketEncryption.KMS if use_sse_kms_key else BucketEncryption.S3_MANAGED),
            block_public_access=BlockPublicAccess.BLOCK_ALL,
            server_access_logs_prefix=f"{bucket_name}/" if server_access_logs_bucket else None,
            server_access_logs_bucket=server_access_logs_bucket,
            versioned=True,
            **kwargs,
        )

        if attrs.require_encryption:
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
        monitoring_bucket: Optional[Bucket] = None
        self.buckets = {}

        if s3.monitoring_bucket:
            monitoring_bucket = self._provision_bucket(
                stack_name, "monitoring", s3.monitoring_bucket, access_control=BucketAccessControl.LOG_DELIVERY_WRITE
            )

            region = cdk.Stack.of(self.scope).region
            monitoring_bucket.grant_put(iam.AccountPrincipal(Fact.require_fact(region, FactName.ELBV2_ACCOUNT)), "*")

            monitoring_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="AWSLogDeliveryWrite",
                    effect=iam.Effect.ALLOW,
                    principals=[iam.ServicePrincipal("delivery.logs.amazonaws.com")],
                    actions=[
                        "s3:PutObject",
                    ],
                    resources=[f"{monitoring_bucket.bucket_arn}/*"],
                    conditions={"StringEquals": {"s3:x-amz-acl": "bucket-owner-full-control"}},
                )
            )

            monitoring_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="AWSLogDeliveryCheck",
                    effect=iam.Effect.ALLOW,
                    principals=[iam.ServicePrincipal("delivery.logs.amazonaws.com")],
                    actions=[
                        "s3:GetBucketAcl",
                        "s3:ListBucket",
                    ],
                    resources=[monitoring_bucket.bucket_arn],
                )
            )

            self.buckets["monitoring"] = monitoring_bucket

        self.buckets.update(
            {
                bucket: self._provision_bucket(stack_name, bucket, attrs, server_access_logs_bucket=monitoring_bucket)
                for bucket, attrs in s3.buckets.items()
            }
        )

        for bucket_id, bucket in self.buckets.items():
            cdk.CfnOutput(self.parent, f"{bucket_id}-output", value=bucket.bucket_name)
