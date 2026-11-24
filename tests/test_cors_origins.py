"""FRONTEND_URL lists the browser origins allowed to call the API."""
from utils.cors import DEV_ORIGINS, allowed_origins


def test_unset_allows_only_development_origins():
    assert allowed_origins(None) == list(DEV_ORIGINS)
    assert allowed_origins("") == list(DEV_ORIGINS)


def test_several_origins_separated_by_commas():
    origins = allowed_origins("http://localhost:8000, https://brandmuse-ai-aniekan-udo.vercel.app")
    assert "http://localhost:8000" in origins
    assert "https://brandmuse-ai-aniekan-udo.vercel.app" in origins


def test_a_trailing_slash_is_removed_because_browsers_never_send_one():
    assert "https://app.vercel.app" in allowed_origins("https://app.vercel.app/")


def test_an_origin_is_listed_once():
    assert allowed_origins("http://localhost:3000").count("http://localhost:3000") == 1
