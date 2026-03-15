import os


def get_backend_base_url() -> str:
    return os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def get_admin_credentials() -> tuple[str, str]:
    return (
        os.environ.get("TEST_ADMIN_EMAIL", ""),
        os.environ.get("TEST_ADMIN_PASSWORD", ""),
    )


def get_user_credentials() -> tuple[str, str]:
    return (
        os.environ.get("TEST_USER_EMAIL", ""),
        os.environ.get("TEST_USER_PASSWORD", ""),
    )
