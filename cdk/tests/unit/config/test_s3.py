import unittest
from copy import deepcopy

from domino_cdk.config import S3

sse_kms_key_id = "some-kms-key"

s3_0_0_0_cfg = {
    "buckets": {
        "bucket1": {
            "auto_delete_objects": True,
            "removal_policy_destroy": True,
            "sse_kms_key_id": sse_kms_key_id,
        },
        "bucket2": {
            "auto_delete_objects": True,
            "removal_policy_destroy": True,
            "sse_kms_key_id": sse_kms_key_id,
        },
    }
}

s3_obj = S3(
    buckets={"bucket1": S3.Bucket(True, True, sse_kms_key_id), "bucket2": S3.Bucket(True, True, sse_kms_key_id)},
    monitoring_bucket=None,
)


class TestConfigS3(unittest.TestCase):
    def test_from_0_0_0(self):
        s3 = S3.from_0_0_0(deepcopy(s3_0_0_0_cfg))
        self.assertEqual(s3, s3_obj)

    def test_all_defaults(self):
        s3_cfg = deepcopy(s3_0_0_0_cfg)
        s3_cfg["buckets"]["bucket1"] = {}
        s3_obj_defaults = deepcopy(s3_obj)
        s3_obj_defaults.buckets["bucket1"] = S3.Bucket(False, False, None)
        s3 = S3.from_0_0_0(s3_cfg)
        self.assertEqual(s3, s3_obj_defaults)

    def test_no_buckets(self):
        self.assertEqual(S3.from_0_0_0({"buckets": {}}), S3(buckets={}, monitoring_bucket=None))
