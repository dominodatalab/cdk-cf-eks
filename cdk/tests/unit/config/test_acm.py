import unittest
from copy import deepcopy

from domino_cdk.config import ACM

acm_0_0_0_cfg = {
    "certificates": {
        [
            {"domain": "testdeploy1", "zone_name": "sandbox.domino.tech"},
            {"domain": "testdeploy2", "zone_name": "sandbox.domino.tech"},
            {"domain": "testdeploy3"},
        ]
    },
}

acm_obj = ACM(
    certificates=[
        ACM.Certificate(domain="testdeploy1", zone_name="sandbox.domino.tech"),
        ACM.Certificate(domain="testdeploy2", zone_name="sandbox.domino.tech"),
        ACM.Certificate(domain="testdeploy3", zone_name=None),
    ]
)


class TestConfigACM(unittest.TestCase):
    def test_from_0_0_0(self):
        acm = ACM.from_0_0_0(deepcopy(acm_0_0_0_cfg))
        self.assertEqual(acm, acm_obj)
