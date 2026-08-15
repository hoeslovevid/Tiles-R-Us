from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .meta import RELEASES_API_URL, SETUP_ASSET, VERSION
from .paths import is_frozen


ProgressFn = Callable[[int, int], None]


@dataclass
class ReleaseInfo:
    tag: str
    version: str
    name: str
    notes: str
    setup_url: str
    html_url: str

    @property
    def newer(self) -> bool:
        return version_is_newer(self.version, VERSION)


def parse_version(value: str) -> tuple[int, ...]:
    text = str(value).strip()
    if text.lower().startswith("v"):
        text = text[1:]
    parts: list[int] = []
    for chunk in text.split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts or (0,))


def version_is_newer(latest: str, current: str) -> bool:
    left = parse_version(latest)
    right = parse_version(current)
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return left > right


def release_from_payload(payload: dict[str, Any]) -> ReleaseInfo:
    tag = str(payload.get("tag_name") or payload.get("name") or "")
    version = tag[1:] if tag.lower().startswith("v") else tag
    assets = payload.get("assets") or []
    setup_url = ""
    for asset in assets:
        if str(asset.get("name", "")) == SETUP_ASSET:
            setup_url = str(asset.get("browser_download_url") or "")
            break
    if not setup_url:
        raise ValueError(f"Latest GitHub release does not include {SETUP_ASSET}.")
    return ReleaseInfo(
        tag=tag,
        version=version,
        name=str(payload.get("name") or tag),
        notes=str(payload.get("body") or ""),
        setup_url=setup_url,
        html_url=str(payload.get("html_url") or ""),
    )


def fetch_latest_release(timeout: int = 15) -> ReleaseInfo:
    request = urllib.request.Request(
        RELEASES_API_URL,
        headers={
            "User-Agent": f"TilesRUs/{VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub returned HTTP {exc.code} while checking for updates.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Could not reach GitHub to check for updates.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub returned an invalid update response.") from exc
    return release_from_payload(payload)


def download_setup(url: str, dest: Path, progress: Optional[ProgressFn] = None, timeout: int = 120) -> Path:
    if not url.startswith("https://"):
        raise ValueError("Update downloads must use HTTPS.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"TilesRUs/{VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with dest.open("wb") as handle:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    return dest


def install_exe_path() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve()
    local = os.environ.get("LOCALAPPDATA", "")
    return Path(local) / "TilesRUs" / "TilesRUs.exe"


def launch_installer_and_relaunch(setup_path: Path) -> None:
    """Start a helper that waits for this process, runs Setup.exe, then relaunches."""
    exe = install_exe_path()
    helper = Path(tempfile.gettempdir()) / "TilesRUs-update.ps1"
    helper.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"$pidToWait = {os.getpid()}",
                f"$setup = {json.dumps(str(setup_path))}",
                f"$exe = {json.dumps(str(exe))}",
                "Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue",
                "Start-Sleep -Seconds 1",
                "$installArgs = @('/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES', '/FORCECLOSEAPPLICATIONS')",
                "Start-Process -FilePath $setup -ArgumentList $installArgs -Wait",
                "if (Test-Path -LiteralPath $exe) { Start-Process -FilePath $exe }",
                "Remove-Item -LiteralPath $setup -Force -ErrorAction SilentlyContinue",
                "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
            ]
        ),
        encoding="utf-8",
    )
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
        ],
        close_fds=False,
        creationflags=flags,
    )


def format_release_summary(release: ReleaseInfo) -> str:
    notes = " ".join(release.notes.strip().split())
    if len(notes) > 280:
        notes = notes[:277] + "…"
    if notes:
        return f"{release.name}\n\n{notes}"
    return release.name
