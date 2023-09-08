from os import environ

from aws_cdk.assertions import Template
from aws_cdk import App, Environment, Stack

from domino_cdk.config import S3
from domino_cdk.provisioners.s3 import DominoS3Provisioner

from . import TestCase


class TestDominoS3Provisioner(TestCase):
    KMS_KEY_ARN = "arn:aws-us-gov:kms:us-west-2:1234567890:key/this-is-my-key-id"

    def setUp(self):
        self.app = App()
        self.stack = Stack(self.app, "S3", env=Environment(region="us-west-2"))
        environ["SKIP_UNDEFINED_BUCKETS"] = "True"

    def test_monitoring_bucket(self):
        s3_config = S3(
            buckets=S3.BucketList(
                blobs=None, logs=None, backups=None, registry=None, monitoring=S3.BucketList.Bucket(True, True, "")
            )
        )

        DominoS3Provisioner(self.stack, "construct-1", "test-s3", s3_config, False)

        assertion = Template.from_stack(self.stack)

        template = self.app.synth().get_stack("S3").template

        assertion.resource_count_is("AWS::S3::Bucket", 1)
        assertion.has_resource(
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
        s3_config = S3(
            buckets=S3.BucketList(
                blobs=None,
                logs=None,
                backups=None,
                registry=None,
                monitoring=S3.BucketList.Bucket(True, True, self.KMS_KEY_ARN),
            )
        )

        DominoS3Provisioner(self.stack, "construct-1", "test-s3", s3_config, False)

        assertion = Template.from_stack(self.stack)
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
                S3.BucketList.Bucket(False, False, "", "test-s3-retain"),
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
                S3.BucketList.Bucket(False, False, self.KMS_KEY_ARN, "test-s3-cmk"),
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
                S3.BucketList.Bucket(True, True, "", "test-s3-destroy"),
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
                buckets=S3.BucketList(
                    blobs=bucket,
                    logs=None,
                    backups=None,
                    registry=None,
                    monitoring=None,
                )
            )

            DominoS3Provisioner(stack, "construct-1", "test-s3", s3_config, False)

            assertion = Template.from_stack(stack)
            assertion.resource_count_is("AWS::S3::Bucket", 1)
            assertion.has_resource("AWS::S3::Bucket", resource_defn)

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
                        "Sid": "DenyIncorrectEncryptionHeader",
                    },
                    {
                        "Action": "s3:PutObject",
                        "Condition": {"Null": {"s3:x-amz-server-side-encryption": "true"}},
                        "Effect": "Deny",
                        "Sid": "DenyUnEncryptedObjectUploads",
                    },
                ],
            )

    def test_buckets_access_logging(self):
        s3_config = S3(
            buckets=S3.BucketList(
                blobs=None,
                logs=S3.BucketList.Bucket(False, False, ""),
                registry=None,
                backups=None,
                monitoring=S3.BucketList.Bucket(False, False, ""),
            )
        )

        DominoS3Provisioner(self.stack, "construct-1", "test-s3", s3_config, False)

        assertion = Template.from_stack(self.stack)
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
                "BucketName": "test-s3-logs",
                "LoggingConfiguration": {
                    "DestinationBucketName": {"Ref": "monitoringF4BD3810"},
                    "LogFilePrefix": "test-s3-logs/",
                },
            },
        )

    @classmethod
    def teardown_class(cls):
        del environ["SKIP_UNDEFINED_BUCKETS"]
