import unittest
from unittest.mock import patch
from copy import deepcopy

from semantic_version import Version

from domino_cdk import __version__
from domino_cdk.config import config_loader, config_template

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
            template = deepcopy(legacy_template)
            c = config_loader(template)
            self.assertEqual(c, legacy_config)
            warn.assert_called_with(
                "Warning: Unused/unsupported config entries in config.vpc: {'bastion': {'enabled': False, 'instance_type': None, 'ingress_ports': None}}"
            )

        with patch("domino_cdk.config.util.log.warning") as warn:
            template = deepcopy(legacy_template)
            del template["vpc"]["bastion"]
            d = config_loader(template)
            warn.assert_not_called()
            self.assertEqual(c, d)

    def test_unspported_schema_version(self):
        with self.assertRaisesRegex(ValueError, "Unsupported schema version: 9.9.9"):
            config_loader({"schema": "9.9.9"})

    def test_version_with_suffix(self):
        c = config_template().render()
        suffixed_schema = f"{Version(__version__).truncate()}-mysuffix0"
        c["schema"] = suffixed_schema
        d = config_loader(c)
        self.assertEqual(d.schema, __version__)

    def test_invalid_version_syntax(self):
        c = config_template().render()
        suffixed_schema = f"{Version(c['schema']).truncate()}mysuffix0"
        c["schema"] = suffixed_schema
        with self.assertRaisesRegex(ValueError, f"Invalid version string: '{suffixed_schema}'"):
            config_loader(c)
