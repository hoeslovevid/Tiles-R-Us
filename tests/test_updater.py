from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tile_reader.updater import parse_version, release_from_payload, version_is_newer


SAMPLE_RELEASE = {
    "tag_name": "v1.4.0",
    "name": "Tiles R Us 1.4.0",
    "html_url": "https://github.com/hoeslovevid/Tiles-R-Us/releases/tag/v1.4.0",
    "body": "Grade faster.",
    "assets": [
        {"name": "TilesRUs-windows.zip", "browser_download_url": "https://example.invalid/zip"},
        {
            "name": "TilesRUs-Setup.exe",
            "browser_download_url": "https://github.com/hoeslovevid/Tiles-R-Us/releases/download/v1.4.0/TilesRUs-Setup.exe",
        },
    ],
}


def test_parse_version_strips_v_prefix() -> None:
    assert parse_version("v1.3.0") == (1, 3, 0)
    assert parse_version("1.3.0") == (1, 3, 0)


def test_version_is_newer() -> None:
    assert version_is_newer("1.4.0", "1.3.0")
    assert not version_is_newer("1.3.0", "1.3.0")
    assert not version_is_newer("1.2.0", "1.3.0")
    assert version_is_newer("1.3.1", "1.3.0")


def test_release_from_payload_picks_setup_exe() -> None:
    release = release_from_payload(SAMPLE_RELEASE)
    assert release.version == "1.4.0"
    assert release.setup_url.endswith("TilesRUs-Setup.exe")
    assert "zip" not in release.setup_url


def test_release_requires_setup_asset() -> None:
    payload = dict(SAMPLE_RELEASE)
    payload["assets"] = [{"name": "TilesRUs-windows.zip", "browser_download_url": "https://example.invalid/zip"}]
    try:
        release_from_payload(payload)
    except ValueError as exc:
        assert "TilesRUs-Setup.exe" in str(exc)
        return
    raise AssertionError("expected ValueError")


def test_download_rejects_non_https() -> None:
    from pathlib import Path
    from tile_reader.updater import download_setup

    try:
        download_setup("http://example.invalid/TilesRUs-Setup.exe", Path("setup.exe"))
    except ValueError as exc:
        assert "HTTPS" in str(exc)
        return
    raise AssertionError("expected ValueError")


if __name__ == "__main__":
    test_parse_version_strips_v_prefix()
    test_version_is_newer()
    test_release_from_payload_picks_setup_exe()
    test_release_requires_setup_asset()
    test_download_rejects_non_https()
    print("ok")
