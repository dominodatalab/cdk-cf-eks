from aws_cdk.assertions import TemplateAssertions
from aws_cdk.core import App, Environment, Stack

from domino_cdk.config import S3
from domino_cdk.provisioners.s3 import DominoS3Provisioner

from . import TestCase


class TestDominoS3Provisioner(TestCase):
    KMS_KEY_ARN = "arn:aws-us-gov:kms:us-west-2:1234567890:key/this-is-my-key-id"

    def test_monitoring_bucket(self):
        app = App()
        stack = Stack(app, "S3", env=Environment(region="us-west-2"))
        s3_config = S3(
            buckets={},
            monitoring_bucket=S3.Bucket(True, True, ""),
        )

        DominoS3Provisioner(stack, "construct-1", "test-s3", s3_config, False)

        assertion = TemplateAssertions.from_stack(stack)

        template = app.synth().get_stack("S3").template

        assertion.resource_count_is("AWS::S3::Bucket", 1)
        assertion.has_resource_definition(
            "AWS::S3::Bucket",
            {
                "Properties": {
                    "BucketName": "test-s3-monitoring",
                    "AccessControl": "LogDeliveryWrite",
                    "BucketEncryption": {
                        "ServerSideEncryptionConfiguration": [
                            {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                        ]
                    },
                    "PublicAccessBlockConfiguration": {
                        "BlockPublicAcls": True,
                        "BlockPublicPolicy": True,
                        "IgnorePublicAcls": True,
                        "RestrictPublicBuckets": True,
                    },
                    "VersioningConfiguration": {"Status": "Enabled"},
                },
                "UpdateReplacePolicy": "Delete",
                "DeletionPolicy": "Delete",
            },
        )

        assertion.resource_count_is("AWS::S3::BucketPolicy", 1)
        policy = self.find_resource(template, "AWS::S3::BucketPolicy")

        statements = policy["Properties"]["PolicyDocument"]["Statement"]
        self.assertPartialMatch(
            statements,
            [
                {
                    "Action": "s3:*",
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    "Effect": "Deny",
                    "Principal": "*",
                },
                {
                    "Action": ["s3:GetBucket*", "s3:List*", "s3:DeleteObject*"],
                    "Effect": "Allow",
                },
                {
                    "Action": ["s3:PutObject*", "s3:Abort*"],
                    "Effect": "Allow",
                },
                {
                    "Action": "s3:PutObject",
                    "Condition": {"StringEquals": {"s3:x-amz-acl": "bucket-owner-full-control"}},
                    "Effect": "Allow",
                    "Principal": {"Service": "delivery.logs.amazonaws.com"},
                    "Sid": "AWSLogDeliveryWrite",
                },
                {
                    "Action": ["s3:GetBucketAcl", "s3:ListBucket"],
                    "Effect": "Allow",
                    "Principal": {"Service": "delivery.logs.amazonaws.com"},
                    "Sid": "AWSLogDeliveryCheck",
                },
            ],
        )

    def test_monitoring_kms_key(self):
        app = App()
        stack = Stack(app, "S3", env=Environment(region="us-west-2"))
        s3_config = S3(
            buckets={},
            monitoring_bucket=S3.Bucket(True, True, self.KMS_KEY_ARN),
        )

        DominoS3Provisioner(stack, "construct-1", "test-s3", s3_config, False)

        assertion = TemplateAssertions.from_stack(stack)
        assertion.resource_count_is("AWS::S3::Bucket", 1)
        assertion.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketName": "test-s3-monitoring",
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": [
                        {
                            "BucketKeyEnabled": True,
                            "ServerSideEncryptionByDefault": {
                                "KMSMasterKeyID": self.KMS_KEY_ARN,
                                "SSEAlgorithm": "aws:kms",
                            },
                        }
                    ]
                },
            },
        )

    def test_buckets(self):
        buckets = [
            (
                "retain",
                S3.Bucket(False, False, ""),
                {
                    "Properties": {
                        "BucketName": "test-s3-retain",
                        "BucketEncryption": {
                            "ServerSideEncryptionConfiguration": [
                                {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                            ]
                        },
                        "PublicAccessBlockConfiguration": {
                            "BlockPublicAcls": True,
                            "BlockPublicPolicy": True,
                            "IgnorePublicAcls": True,
                            "RestrictPublicBuckets": True,
                        },
                        "VersioningConfiguration": {"Status": "Enabled"},
                    },
                    "UpdateReplacePolicy": "Retain",
                    "DeletionPolicy": "Retain",
                },
            ),
            (
                "cmk",
                S3.Bucket(False, False, self.KMS_KEY_ARN),
                {
                    "Properties": {
                        "BucketName": "test-s3-cmk",
                        "BucketEncryption": {
                            "ServerSideEncryptionConfiguration": [
                                {
                                    "BucketKeyEnabled": True,
                                    "ServerSideEncryptionByDefault": {
                                        "KMSMasterKeyID": self.KMS_KEY_ARN,
                                        "SSEAlgorithm": "aws:kms",
                                    },
                                }
                            ]
                        },
                        "PublicAccessBlockConfiguration": {
                            "BlockPublicAcls": True,
                            "BlockPublicPolicy": True,
                            "IgnorePublicAcls": True,
                            "RestrictPublicBuckets": True,
                        },
                        "VersioningConfiguration": {"Status": "Enabled"},
                    },
                    "UpdateReplacePolicy": "Retain",
                    "DeletionPolicy": "Retain",
                },
            ),
            (
                "destroy",
                S3.Bucket(True, True, ""),
                {
                    "Properties": {
                        "BucketName": "test-s3-destroy",
                        "BucketEncryption": {
                            "ServerSideEncryptionConfiguration": [
                                {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                            ]
                        },
                        "PublicAccessBlockConfiguration": {
                            "BlockPublicAcls": True,
                            "BlockPublicPolicy": True,
                            "IgnorePublicAcls": True,
                            "RestrictPublicBuckets": True,
                        },
                        "VersioningConfiguration": {"Status": "Enabled"},
                    },
                    "UpdateReplacePolicy": "Delete",
                    "DeletionPolicy": "Delete",
                },
                {
                    "Action": ["s3:GetBucket*", "s3:List*", "s3:DeleteObject*"],
                    "Effect": "Allow",
                },
            ),
        ]

        for (name, bucket, resource_defn, *policies) in buckets:
            app = App()
            stack = Stack(app, "S3", env=Environment(region="us-west-2"))
            s3_config = S3(
                buckets={name: bucket},
                monitoring_bucket=None,
            )

            DominoS3Provisioner(stack, "construct-1", "test-s3", s3_config, False)

            assertion = TemplateAssertions.from_stack(stack)
            assertion.resource_count_is("AWS::S3::Bucket", 1)
            assertion.has_resource_definition("AWS::S3::Bucket", resource_defn)

            assertion.resource_count_is("AWS::S3::BucketPolicy", 1)

            template = app.synth().get_stack("S3").template
            policy = self.find_resource(template, "AWS::S3::BucketPolicy")

            statements = policy["Properties"]["PolicyDocument"]["Statement"]
            self.assertPartialMatch(
                statements,
                [
                    {
                        "Action": "s3:*",
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                        "Effect": "Deny",
                        "Principal": "*",
                    },
                    *policies,
                    {
                        "Action": "s3:PutObject",
                        "Condition": {
                            "StringNotEquals": {
                                "s3:x-amz-server-side-encryption": "aws:kms" if bucket.sse_kms_key_id else "AES256"
                            }
                        },
                        "Effect": "Deny",
                        "Principal": "*",
                        "Sid": "DenyIncorrectEncryptionHeader",
                    },
                    {
                        "Action": "s3:PutObject",
                        "Condition": {"Null": {"s3:x-amz-server-side-encryption": "true"}},
                        "Effect": "Deny",
                        "Principal": "*",
                        "Sid": "DenyUnEncryptedObjectUploads",
                    },
                ],
            )

    def test_buckets_access_logging(self):
        app = App()
        stack = Stack(app, "S3", env=Environment(region="us-west-2"))
        s3_config = S3(
            buckets={"logged": S3.Bucket(False, False, "")},
            monitoring_bucket=S3.Bucket(False, False, ""),
        )

        DominoS3Provisioner(stack, "construct-1", "test-s3", s3_config, False)

        assertion = TemplateAssertions.from_stack(stack)
        assertion.resource_count_is("AWS::S3::Bucket", 2)
        assertion.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketName": "test-s3-monitoring",
            },
        )

        assertion.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "BucketName": "test-s3-logged",
                "LoggingConfiguration": {
                    "DestinationBucketName": {"Ref": "monitoringF4BD3810"},
                    "LogFilePrefix": "test-s3-logged/",
                },
            },
        )
