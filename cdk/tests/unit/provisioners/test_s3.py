from typing import Any, Dict, Optional
from unittest import TestCase

from aws_cdk.assertions import TemplateAssertions
from aws_cdk.core import App, Environment, Stack

from domino_cdk.config import S3
from domino_cdk.provisioners.s3 import DominoS3Provisioner


def find_resource(template: Dict, typ: str, matchers: Dict = None) -> Optional[Dict]:
    return next(
        (
            res
            for _, res in template.get("Resources", {}).items()
            if res["Type"] == typ and all(m in res.items() for m in (matchers or {}).items())
        ),
        None,
    )


class TestDominoS3Provisioner(TestCase):
    def assertPartialMatch(self, obj: Any, matchers: Any) -> None:
        self.assertEqual(type(obj), type(matchers))

        if isinstance(obj, list):
            self.assertEqual(len(obj), len(matchers))
            for i, left in enumerate(obj):
                self.assertPartialMatch(left, matchers[i])
        elif isinstance(obj, dict):
            for m in matchers.items():
                self.assertIn(m, obj.items())
        else:
            self.assertEqual(obj, matchers)

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
        policy = find_resource(template, "AWS::S3::BucketPolicy")

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
