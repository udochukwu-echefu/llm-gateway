from loadtest.runtime import ROOT


def test_build_context_excludes_benchmark_credentials_and_real_env() -> None:
    patterns = (ROOT / ".dockerignore").read_text().splitlines()

    assert ".env" in patterns
    assert ".env.*" in patterns
    assert "loadtest/.state" in patterns
    assert "loadtest/results" in patterns


def test_fake_server_has_no_external_provider_imports_or_request_echo() -> None:
    source = (ROOT / "loadtest/fake_provider/app.py").read_text()

    assert "llm_gateway.providers" not in source
    assert "httpx" not in source
    assert "messages" not in source
