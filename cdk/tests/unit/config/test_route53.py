import unittest
from copy import deepcopy

from domino_cdk.config import Route53

zone_id = "some_zone_id"

r53_0_0_0_cfg = {"zone_ids": [zone_id]}

r53_obj = Route53(zone_ids=[zone_id])


class TestConfigRoute53(unittest.TestCase):
    def test_from_0_0_0(self):
        r53 = Route53.from_0_0_0(deepcopy(r53_0_0_0_cfg))
        self.assertEqual(r53, r53_obj)

    def test_no_zones(self):
        r53 = Route53.from_0_0_0({})
        self.assertEqual(r53, Route53(zone_ids=None))
