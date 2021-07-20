from dataclasses import dataclass
from typing import Dict

import aws_cdk.aws_logs as logs
import aws_cdk.custom_resources as cr
from aws_cdk import core as cdk


@dataclass
class DeviceMapping:
    name: str


ami_map: Dict[str, DeviceMapping] = {}


def root_device_mapping(scope: cdk.Construct, ami_id: str) -> DeviceMapping:
    if device_mapping := ami_map.get(ami_id):
        return device_mapping

    root_device_name_cr = cr.AwsCustomResource(
        scope,
        f"ImageRootDeviceName-{ami_id}",
        log_retention=logs.RetentionDays.ONE_DAY,
        policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
        on_update=cr.AwsSdkCall(
            action="describeImages",
            service="EC2",
            output_paths=["Images.0.RootDeviceName"],
            parameters={
                "ImageIds": [ami_id],
            },
            physical_resource_id=cr.PhysicalResourceId.of(f"ImageRootDeviceName-{ami_id}"),
        ),
    )

    root_device_name = root_device_name_cr.get_response_field("Images.0.RootDeviceName")
    ami_map[ami_id] = DeviceMapping(root_device_name)
    return ami_map[ami_id]
