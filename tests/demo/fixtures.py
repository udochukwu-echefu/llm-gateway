"""Synthetic appliance configuration shared by process/config tests."""


def demo_environment() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql://demo:synthetic-password@db.fake.invalid/demo",
        "REDIS_URL": "rediss://cache.fake.invalid:6379/0",
        "GATEWAY_API_KEY_PEPPER": "synthetic-placeholder-pepper-at-least-32-bytes",
        "GATEWAY_CACHE_ENCRYPTION_KEY": "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=",
        "ADMIN_CONSOLE_SESSION_SECRET": "synthetic-placeholder-session-at-least-32-bytes",
        "ADMIN_CONSOLE_ORIGIN": "https://demo.example.invalid",
    }
