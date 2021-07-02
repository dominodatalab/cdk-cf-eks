import unittest
from typing import Any, Dict, Optional


class TestCase(unittest.TestCase):
    @staticmethod
    def find_resource(template: Dict, typ: str, matchers: Dict = None) -> Optional[Dict]:
        return next(
            (
                res
                for _, res in template.get("Resources", {}).items()
                if res["Type"] == typ and all(m in res.items() for m in (matchers or {}).items())
            ),
            None,
        )

    def assertPartialMatch(self, obj: Any, matchers: Any) -> None:
        self.assertEqual(type(obj), type(matchers))

        if isinstance(obj, list):
            self.assertEqual(len(obj), len(matchers))
            for i, left in enumerate(obj):
                self.assertPartialMatch(left, matchers[i])
        elif isinstance(obj, dict):
            for m in matchers.items():
                self.assertIn(m, obj.items())
        else:
            self.assertEqual(obj, matchers)
