import unittest
from copy import deepcopy
from unittest.mock import patch

from domino_cdk.config.util import IngressRule, check_leavins, from_loader

ingress_rules = [{"name": "some_rule", "from_port": 22, "to_port": 22, "protocol": "TCP", "ip_cidrs": ["10.0.0.0/16"]}]

ingress_rule_object = IngressRule("some_rule", 22, 22, "TCP", ["10.0.0.0/16"])


class TestConfigUtil(unittest.TestCase):
    def test_from_loader(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            test_thing = "arbitrary_variable"
            x = from_loader("myname", test_thing, {})
            warn.assert_not_called()
            self.assertEqual(x, test_thing)

    def test_from_loader_warning(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            test_thing = "arbitrary_variable"
            x = from_loader("myname", test_thing, {'boing': 'peng'})
            warn.assert_called_with("Warning: Unused/unsupported config entries in myname: {'boing': 'peng'}")
            self.assertEqual(x, test_thing)

    def test_check_leavins_list(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            check_leavins("mything", "mysection", [])
            warn.assert_not_called()

    def test_check_leavins_list_nonempty(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            check_leavins("mything", "mysection", ["some_value"])
            warn.assert_called_with("Warning: Unused/unsupported mything in mysection: ['some_value']")

    def test_check_leavins_dict(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            check_leavins("mything", "mysection", {})
            warn.assert_not_called()

    def test_check_leavins_dict_nonempty(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            check_leavins("mything", "mysection", {"some": "value"})
            warn.assert_called_with("Warning: Unused/unsupported mything in mysection: ['some']")

    def test_ingress_rule_loading(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            loaded_rules = IngressRule.load_rules("some_name", deepcopy(ingress_rules))
            self.assertEqual(loaded_rules, [ingress_rule_object])
            warn.assert_not_called()

    def test_ingress_rule_loading_extra_args(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            rules = deepcopy(ingress_rules)
            rules[0]["extra"] = "boing"
            loaded_rules = IngressRule.load_rules("some_name", rules)
            self.assertEqual(loaded_rules, [ingress_rule_object])
            warn.assert_called_with("Warning: Unused/unsupported ingress rules in some_name: [{'extra': 'boing'}]")

    def test_ingress_rule_loading_none(self):
        loaded_rules = IngressRule.load_rules("some_name", None)
        self.assertEqual(loaded_rules, None)
