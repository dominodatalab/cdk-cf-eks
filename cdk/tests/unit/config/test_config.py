import unittest
from unittest.mock import patch

from domino_cdk.config import config_loader, config_template
from domino_cdk.config.util import IngressRule

from . import default_config, legacy_config, legacy_template


class TestConfig(unittest.TestCase):
    def test_default_template(self):
        c = config_template()
        self.assertEqual(c, default_config)

    def test_round_trip_template(self):
        c = config_template()
        d = config_loader(c.render())
        self.assertEqual(c, d)

    def test_legacy_template(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            c = config_loader(legacy_template)
            self.assertEqual(c, legacy_config)
            warn.assert_called_with(
                "Warning: Unused/unsupported config entries in config.vpc: {'bastion': {'enabled': False, 'instance_type': None, 'ingress_ports': None}}"
            )

        with patch("domino_cdk.config.util.log.warning") as warn:
            rendered_template = c.render()
            rendered_template["schema"] = "0.0.0"
            rendered_template["eks"]["nodegroups"] = rendered_template["eks"]["unmanaged_nodegroups"]
            del rendered_template["eks"]["unmanaged_nodegroups"]
            del rendered_template["vpc"]["bastion"]
            d = config_loader(rendered_template)
            warn.assert_not_called()
            self.assertEqual(c, d)

    def test_ingress_rule_loading(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            rules = [
                {"name": "some_rule", "from_port": 22, "to_port": 22, "protocol": "TCP", "ip_cidrs": ["10.0.0.0/16"]}
            ]
            loaded_rules = IngressRule.load_rules("some_name", rules)
            self.assertEqual(loaded_rules, [IngressRule("some_rule", 22, 22, "TCP", ["10.0.0.0/16"])])
            warn.assert_not_called()

    def test_ingress_rule_loading_extra_args(self):
        with patch("domino_cdk.config.util.log.warning") as warn:
            rules = [
                {
                    "name": "some_rule",
                    "from_port": 22,
                    "to_port": 22,
                    "protocol": "TCP",
                    "ip_cidrs": ["10.0.0.0/16"],
                    "extra": "boing",
                }
            ]
            loaded_rules = IngressRule.load_rules("some_name", rules)
            self.assertEqual(loaded_rules, [IngressRule("some_rule", 22, 22, "TCP", ["10.0.0.0/16"])])
            warn.assert_called_with("Warning: Unused/unsupported ingress rules in some_name: [{'extra': 'boing'}]")

    def test_ingress_rule_loading_none(self):
        loaded_rules = IngressRule.load_rules("some_name", None)
        self.assertEqual(loaded_rules, None)

    def test_managed_nodegroup_extra_args(self):
        test_group = {
            "disk_size": 20,
            "min_size": 1,
            "max_size": 1,
            "instance_types": ["t2.micro"],
            "labels": {},
            "tags": {},
            "spot": False,
            "desired_size": 1,
        }

        with patch("domino_cdk.config.util.log.warning") as warn:
            c = config_template().render()
            c["eks"]["managed_nodegroups"] = {"test_group": dict(test_group)}
            config_loader(dict(c))
            warn.assert_not_called()

        with patch("domino_cdk.config.util.log.warning") as warn:
            c = config_template().render()
            c["eks"]["managed_nodegroups"] = {"test_group": dict(test_group)}
            c["eks"]["managed_nodegroups"]["test_group"]["extra_arg"] = "boing"
            config_loader(dict(c))
            warn.assert_called_with(
                "Warning: Unused/unsupported managed nodegroup attribute in config.eks.unmanaged_nodegroups: ['extra_arg']"
            )
