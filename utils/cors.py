"""Which browser origins may call the API."""

DEV_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def allowed_origins(frontend_url: str | None) -> list[str]:
    """The development origins plus every origin listed in FRONTEND_URL.

    FRONTEND_URL takes one origin or several separated by commas, e.g. the
    Vercel address and a custom domain. A trailing slash is removed: browsers
    send the origin without one, so "https://app.vercel.app/" would never match.
    """
    origins = list(DEV_ORIGINS)
    for origin in (frontend_url or "").split(","):
        origin = origin.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)
    return origins
