import unittest
from copy import deepcopy

from domino_cdk.config import EFS

efs_0_0_0_cfg = {
    "backup": {
        "enable": True,
        "schedule": "0 12 * * ? *",
        "move_to_cold_storage_after": 35,
        "delete_after": 125,
        "removal_policy": "DESTROY",
    },
    "removal_policy_destroy": True,
}

efs_obj = EFS(
    backup=EFS.Backup(
        enable=True, schedule="0 12 * * ? *", move_to_cold_storage_after=35, delete_after=125, removal_policy="DESTROY"
    ),
    removal_policy_destroy=True,
)


class TestConfigEFS(unittest.TestCase):
    def test_from_0_0_0(self):
        efs = EFS.from_0_0_0(deepcopy(efs_0_0_0_cfg))
        self.assertEqual(efs, efs_obj)
