"""Owner-run provisioning: locally generated values go to CLI stdin, never terminal/files."""

import base64
import secrets
import shutil
import subprocess


def set_secrets() -> None:
    cli = shutil.which("insta")
    if cli is None:
        raise RuntimeError("Install the InstaCloud CLI before provisioning secrets.")
    values = {
        "GATEWAY_API_KEY_PEPPER": secrets.token_urlsafe(48),
        "GATEWAY_CACHE_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "ADMIN_CONSOLE_SESSION_SECRET": secrets.token_urlsafe(48),
    }
    for name, value in values.items():
        result = subprocess.run(  # noqa: S603 -- fixed CLI; secret is stdin, never argv
            [cli, "--agent", "secrets", "set", name, "--service", "compute/appliance"],
            input=value.encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Could not set {name}; check CLI authentication/governance.")
    print("Three generated appliance secrets set; no values printed or written.")


if __name__ == "__main__":
    set_secrets()
