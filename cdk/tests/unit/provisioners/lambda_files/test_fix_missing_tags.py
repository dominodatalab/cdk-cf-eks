from json import dumps
from os import environ
from unittest import TestCase
from unittest.mock import ANY, patch

import boto3
import cfnresponse
from awslambdaric.lambda_context import LambdaContext
from moto import mock_ec2, mock_iam

from domino_cdk.provisioners.lambda_files import fix_missing_tags
from domino_cdk.util import DominoCdkUtil


@mock_ec2
@mock_iam
@patch.dict(
    environ,
    {
        "AWS_LAMBDA_LOG_GROUP_NAME": "my-log-group",
        "AWS_LAMBDA_LOG_STREAM_NAME": "my-log-stream",
        "AWS_LAMBDA_FUNCTION_NAME": "fix-missing-tags",
        "AWS_LAMBDA_FUNCTION_MEMORY_SIZE": "100",
        "AWS_LAMBDA_FUNCTION_VERSION": "1",
        "AWS_DEFAULT_REGION": "us-west-2",
    },
    clear=True,
)
class TestFixMissingTags(TestCase):
    default_event = {
        "RequestType": "Create",
        "StackId": "my-stack-1",
        "RequestId": "request-id",
        "LogicalResourceId": "logical-resource-id",
        "ResourceProperties": {
            "stack_name": "mystack",
            "untagged_resources": {"ec2": [], "iam": []},
            "tags": {"my-tag": "one"},
            "vpc_id": "vpc-12345",
        },
        "ResponseURL": "https://cfn.example.com",
    }

    @property
    def default_context(self):
        return LambdaContext("invoke-id", {}, {}, 100)

    default_response = {
        "Status": cfnresponse.SUCCESS,
        "Reason": "See the details in CloudWatch Log Stream: my-log-stream",
        "PhysicalResourceId": "domino-tag-fixer-mystack",
        "StackId": "my-stack-1",
        "RequestId": "request-id",
        "LogicalResourceId": "logical-resource-id",
        "NoEcho": False,
        "Data": {},
    }

    @property
    def default_vpc(self):
        return self.ec2_client.describe_vpcs()["Vpcs"][0]

    def setUp(self):
        self.ec2_client = boto3.client("ec2", region_name="us-west-2")

        self.vpc_endpoint = self.ec2_client.create_vpc_endpoint(
            VpcEndpointType="Interface", VpcId=self.default_vpc["VpcId"], ServiceName="s3"
        )

        self.iam_client = boto3.client("iam", region_name="us-west-2")
        self.iam_policy = self.iam_client.create_policy(
            PolicyName="my-policy",
            PolicyDocument='{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["ec2:*"], "Resource": "*"}]}',
        )

    @patch("urllib3.PoolManager.request")
    def test_on_event_empty(self, mock_request):
        for event in ["Create", "Update", "Delete"]:
            with self.subTest(event):
                mock_request.reset_mock()
                fix_missing_tags.on_event(self.default_event | {"RequestType": event}, self.default_context)
                mock_request.assert_called_with(
                    "PUT",
                    "https://cfn.example.com",
                    body=dumps(self.default_response).encode(),
                    headers=ANY,
                )

    @patch("urllib3.PoolManager.request")
    def test_on_event_resources(self, mock_request):
        for event in ["Create", "Update"]:
            with self.subTest(event):
                fix_missing_tags.on_event(
                    DominoCdkUtil.deep_merge(
                        self.default_event,
                        {
                            "RequestType": event,
                            "ResourceProperties": {
                                "vpc_id": self.default_vpc["VpcId"],
                                "untagged_resources": {"iam": [self.iam_policy["Policy"]["Arn"]]},
                            },
                        },
                    ),
                    self.default_context,
                )
                mock_request.assert_called_with(
                    "PUT",
                    "https://cfn.example.com",
                    body=dumps(self.default_response).encode(),
                    headers=ANY,
                )

                tags = [{"Key": "my-tag", "Value": "one"}]

                self.assertEqual(tags, self.ec2_client.describe_route_tables()["RouteTables"][0]["Tags"])
                self.assertEqual(tags, self.ec2_client.describe_security_groups()["SecurityGroups"][0]["Tags"])
                self.assertEqual(tags, self.ec2_client.describe_network_acls()["NetworkAcls"][0]["Tags"])
                self.assertEqual(tags, self.ec2_client.describe_vpc_endpoints()["VpcEndpoints"][0]["Tags"])
                self.assertEqual(
                    tags, self.iam_client.get_policy(PolicyArn=self.iam_policy["Policy"]["Arn"])["Policy"]["Tags"]
                )
