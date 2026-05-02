def service_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def internal_url(base_url: str, path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{service_url(base_url)}{path}"
