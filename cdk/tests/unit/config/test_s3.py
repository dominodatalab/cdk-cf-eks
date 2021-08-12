import unittest
from copy import deepcopy

from domino_cdk.config import S3

sse_kms_key_id = "some-kms-key"

s3_0_0_0_cfg = {
    "buckets": {
        "blobs": {
            "auto_delete_objects": True,
            "removal_policy_destroy": True,
            "sse_kms_key_id": sse_kms_key_id,
        },
        "logs": {
            "auto_delete_objects": True,
            "removal_policy_destroy": True,
            "sse_kms_key_id": sse_kms_key_id,
        },
        "backups": {
            "auto_delete_objects": True,
            "removal_policy_destroy": True,
            "sse_kms_key_id": sse_kms_key_id,
        },
        "registry": {
            "auto_delete_objects": True,
            "removal_policy_destroy": True,
            "sse_kms_key_id": sse_kms_key_id,
        },
        "monitoring": {
            "auto_delete_objects": True,
            "removal_policy_destroy": True,
            "sse_kms_key_id": sse_kms_key_id,
        },
    }
}

s3_obj = S3(
    buckets=S3.BucketList(
        blobs=S3.BucketList.Bucket(
            auto_delete_objects=True, removal_policy_destroy=True, sse_kms_key_id=sse_kms_key_id
        ),
        logs=S3.BucketList.Bucket(auto_delete_objects=True, removal_policy_destroy=True, sse_kms_key_id=sse_kms_key_id),
        backups=S3.BucketList.Bucket(
            auto_delete_objects=True, removal_policy_destroy=True, sse_kms_key_id=sse_kms_key_id
        ),
        registry=S3.BucketList.Bucket(
            auto_delete_objects=True, removal_policy_destroy=True, sse_kms_key_id=sse_kms_key_id
        ),
        monitoring=S3.BucketList.Bucket(
            auto_delete_objects=True, removal_policy_destroy=True, sse_kms_key_id=sse_kms_key_id
        ),
    )
)


class TestConfigS3(unittest.TestCase):
    def test_from_0_0_0(self):
        s3 = S3.from_0_0_0(deepcopy(s3_0_0_0_cfg))
        self.assertEqual(s3, s3_obj)

    def test_bucket_defaults(self):
        s3_cfg = deepcopy(s3_0_0_0_cfg)
        s3_cfg["buckets"]["blobs"] = {}
        s3_cfg["buckets"]["monitoring"] = None
        s3_obj_defaults = deepcopy(s3_obj)
        s3_obj_defaults.buckets.blobs = S3.BucketList.Bucket(False, False, None, None)
        s3_obj_defaults.buckets.monitoring = None
        s3 = S3.from_0_0_0(s3_cfg)
        self.assertEqual(s3, s3_obj_defaults)

    def test_no_buckets(self):
        s3_cfg = deepcopy(s3_0_0_0_cfg)
        s3_cfg["buckets"]["blobs"] = None
        s3_cfg["buckets"]["logs"] = None
        s3_cfg["buckets"]["backups"] = None
        s3_cfg["buckets"]["registry"] = None

        with self.assertRaisesRegex(ValueError, "No definition for blobs.*logs.*backups.*registry bucket"):
            S3.from_0_0_0(s3_cfg)
