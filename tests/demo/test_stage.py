"""Exercise the deployment helper with a disposable Git repository and a fake CLI."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def staged_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo with spaces"
    demo = repo / "deploy/demo"
    demo.mkdir(parents=True)
    shutil.copyfile(Path("deploy/demo/stage.sh"), demo / "stage.sh")
    (demo / "Dockerfile").write_text("FROM synthetic-demo\n")
    (repo / "Dockerfile").write_text("FROM wrong-root-image\n")
    (repo / ".gitignore").write_text(".env\n.demo-keys.env\n.insta/\n.claude/\n.codex/\n")
    _run(["git", "init", "-q", str(repo)])
    _run(["git", "-C", str(repo), "add", "."])
    _run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "Synthetic staging fixture",
        ]
    )
    for name in (".env", ".demo-keys.env"):
        (repo / name).write_text("synthetic-local-only\n")
    for name in (".insta", ".claude", ".codex"):
        (repo / name).mkdir()
        (repo / name / "local-only").write_text("synthetic-local-only\n")
    cli = tmp_path / "bin/insta"
    cli.parent.mkdir()
    cli.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$STAGE_CALLS"\n'
        'printf "%s\\n" "$3" > "$STAGE_PATH"\n'
        'if [ "$2" = build ]; then cp -R "$3" "$STAGE_CAPTURE"; fi\n'
        'if [ "${STAGE_FAIL:-}" = "$2" ]; then exit 7; fi\n'
        'if [ "$2" = deploy ]; then echo https://synthetic-demo.example.invalid; fi\n'
    )
    cli.chmod(0o755)
    env = {
        "PATH": str(cli.parent) + os.pathsep + os.environ.get("PATH", ""),
        "TMPDIR": str(tmp_path),
        "STAGE_CALLS": str(tmp_path / "calls"),
        "STAGE_PATH": str(tmp_path / "stage-path"),
        "STAGE_CAPTURE": str(tmp_path / "capture"),
    }
    return repo, env


def test_stage_archives_only_committed_code_and_prints_deployment_url(
    staged_repo: tuple[Path, dict[str, str]],
) -> None:
    repo, env = staged_repo

    result = _run(["bash", str(repo / "deploy/demo/stage.sh")], env=env)

    assert result.returncode == 0
    assert "https://synthetic-demo.example.invalid" in result.stdout
    capture = Path(env["STAGE_CAPTURE"])
    assert (capture / "Dockerfile").read_text() == "FROM synthetic-demo\n"
    assert all(
        not (capture / name).exists()
        for name in (
            ".git",
            ".env",
            ".demo-keys.env",
            ".insta",
            ".claude",
            ".codex",
        )
    )
    stage = Path(Path(env["STAGE_PATH"]).read_text().strip())
    assert not stage.exists()
    assert Path(env["STAGE_CALLS"]).read_text().splitlines() == [
        f"--agent build {stage} --port 3000",
        f"--agent deploy {stage} --group appliance --port 3000",
    ]


@pytest.mark.parametrize("dirty", ["tracked", "staged", "untracked"])
def test_stage_refuses_every_kind_of_dirty_tree_without_calling_cli(
    staged_repo: tuple[Path, dict[str, str]],
    dirty: str,
) -> None:
    repo, env = staged_repo
    file = repo / ("untracked.txt" if dirty == "untracked" else "Dockerfile")
    file.write_text("changed\n")
    if dirty == "staged":
        _run(["git", "-C", str(repo), "add", "Dockerfile"])

    result = _run(["bash", str(repo / "deploy/demo/stage.sh")], env=env)

    assert result.returncode == 1
    assert "dirty working tree" in result.stderr
    assert not Path(env["STAGE_CALLS"]).exists()


@pytest.mark.parametrize("failure", ["build", "deploy"])
def test_stage_cleans_temporary_context_and_propagates_cli_failure(
    staged_repo: tuple[Path, dict[str, str]],
    failure: str,
) -> None:
    repo, env = staged_repo

    result = _run(["bash", str(repo / "deploy/demo/stage.sh")], env={**env, "STAGE_FAIL": failure})

    assert result.returncode == 7
    assert not Path(Path(env["STAGE_PATH"]).read_text().strip()).exists()
    assert len(Path(env["STAGE_CALLS"]).read_text().splitlines()) == (
        1 if failure == "build" else 2
    )


def _run(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- test-owned Git fixture and fake CLI; no deployment
        args,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
