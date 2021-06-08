from dataclasses import dataclass
from typing import List

def from_loader(name: str, cfg, c: dict):
    if c:
        print(f"Warning: Unused/unsupported config entries in {name}: {c}")
    return cfg


@dataclass
class MachineImage:
    ami_id: str
    user_data: str


@dataclass
class IngressRule:
    name: str
    from_port: int
    to_port: 22
    protocol: str
    ip_cidrs: List[str]

    @staticmethod
    def load_rules(name: str, rules: List[dict]):
        output = [IngressRule(r.pop("name"), r.pop("from_port"), r.pop("to_port"), r.pop("protocol"), r.pop("ip_cidrs")) for r in rules]
        if rule_leavins := [r for r in rules if r]:
            print(f"Warning: Unused/unsupported ingress rules in {name}: {rule_leavins}")
        return output
