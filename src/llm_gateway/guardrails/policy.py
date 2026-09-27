"""Defaults are a floor: neither organization nor team may weaken them."""

from dataclasses import dataclass
from typing import Literal, get_args

Detector = Literal[
    "secret_api_key", "secret_private_key", "email", "phone", "card_number", "iban", "ip_address"
]
Action = Literal["allow", "redact", "block"]
Region = Literal["us", "eu", "cn", "global", "unknown"]
DETECTORS: tuple[Detector, ...] = get_args(Detector)
REGIONS: tuple[Region, ...] = get_args(Region)
ACTIONS: tuple[Action, ...] = get_args(Action)
DEFAULTS: dict[Detector, Action] = {
    "secret_api_key": "block",
    "secret_private_key": "block",
    "email": "allow",
    "phone": "allow",
    "card_number": "redact",
    "iban": "redact",
    "ip_address": "allow",
}


@dataclass(frozen=True)
class GuardrailPolicy:
    organization: tuple[tuple[Detector, Action], ...] = ()
    team: tuple[tuple[Detector, Action], ...] = ()

    def action(self, detector: Detector) -> Action:
        choices: list[Action] = [DEFAULTS[detector]]
        choices.extend(
            action for name, action in (*self.organization, *self.team) if name == detector
        )
        return max(choices, key=ACTIONS.index)


def parse_actions(values: list[str]) -> tuple[tuple[Detector, Action], ...]:
    result: dict[Detector, Action] = {}
    for value in values:
        name, _, action = value.partition("=")
        if name not in DETECTORS or action not in ACTIONS:
            raise ValueError("Actions must be a known detector=allow|redact|block")
        result[name] = action
    return tuple(result.items())


def parse_regions(values: list[str] | None) -> tuple[Region, ...] | None:
    if values is None:
        return None
    result: list[Region] = []
    for value in values:
        if value not in REGIONS:
            raise ValueError("Regions must be us, eu, cn, global or unknown")
        if value not in result:
            result.append(value)
    return tuple(result)
