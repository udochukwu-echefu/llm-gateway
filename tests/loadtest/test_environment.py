from pathlib import Path

from loadtest.environment import source_hash


def test_source_hash_changes_with_code_but_ignores_secrets(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('synthetic')")
    first = source_hash(tmp_path)
    (tmp_path / ".env").write_text("not-source")

    assert source_hash(tmp_path) == first
    (tmp_path / "app.py").write_text("print('changed')")
    assert source_hash(tmp_path) != first


def test_source_hash_includes_limiter_lua(tmp_path: Path) -> None:
    first = source_hash(tmp_path)
    (tmp_path / "gcra.lua").write_text("return {1}")
    assert source_hash(tmp_path) != first
