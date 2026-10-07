from pathlib import Path

PAGE = Path("boneio/migrations/assets/docker/nodered/caddy/502.html")


def test_the_page_refreshes_itself():
    """Shown while boneIO starts; nobody should have to press anything."""
    assert '<meta http-equiv="refresh" content="3">' in PAGE.read_text(encoding="utf-8")


def test_the_page_says_starting_in_both_languages():
    text = PAGE.read_text(encoding="utf-8")
    assert "boneIO is starting" in text
    assert "boneIO startuje" in text


def test_the_page_loads_nothing_from_outside():
    """Served before anything else is up, often with no internet."""
    text = PAGE.read_text(encoding="utf-8")
    assert "http://" not in text and "https://" not in text
