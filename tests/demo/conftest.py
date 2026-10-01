"""Appliance boots need their own database so history/keys cannot pollute other suites."""

from collections.abc import Callable, Iterator
from typing import cast

import pytest

from tests.conftest import migrated_database as create_disposable_database


@pytest.fixture
def migrated_database() -> Iterator[str]:
    factory = cast(Callable[[], Iterator[str]], getattr(create_disposable_database, "__wrapped__"))  # noqa: B009 -- pytest's runtime wrapper is absent from its public type
    yield from factory()
