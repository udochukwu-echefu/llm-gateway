import argparse

import pytest

from llm_gateway.guardrails.commands import add_commands
from llm_gateway.guardrails.policy import parse_regions


def test_sg_is_accepted_and_duplicates_are_normalized() -> None:
    assert parse_regions(["sg", "eu", "sg"]) == ("sg", "eu")


def test_invalid_region_error_lists_sg() -> None:
    with pytest.raises(ValueError, match="us, eu, cn, sg, global, unknown"):
        parse_regions(["singapore"])


def test_cli_residency_help_and_choices_include_sg() -> None:
    parser = argparse.ArgumentParser(prog="gateway-admin set-residency")
    add_commands(parser)

    args = parser.parse_args(["example", "--allow-region", "sg"])

    assert args.allow_region == ["sg"]
    assert "sg" in parser.format_help()
