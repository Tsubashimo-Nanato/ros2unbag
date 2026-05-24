from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GITHUB_API_ROOT = "https://api.github.com/repos/Tsubashimo-Nanato/ros2unbag"
PROJECT_NAME = "ros2unbag"


@dataclass(slots=True)
class UpdateInfo:
    current_version: str
    latest_version: str | None
    latest_ref: str | None
    latest_url: str | None
    changes: str
    update_available: bool
    source: str
    error: str | None = None


def current_version() -> str:
    try:
        return version(PROJECT_NAME)
    except PackageNotFoundError:
        return "unknown"


def check_for_update(
    *,
    current: str | None = None,
    timeout: float = 5.0,
    urlopen_factory: Callable[..., Any] = urlopen,
) -> UpdateInfo:
    installed = current or current_version()
    try:
        release = _fetch_json(
            f"{GITHUB_API_ROOT}/releases/latest",
            timeout=timeout,
            urlopen_factory=urlopen_factory,
        )
        latest_ref = str(release.get("tag_name") or "").strip() or None
        latest_version = _normalize_version(latest_ref)
        return UpdateInfo(
            current_version=installed,
            latest_version=latest_version,
            latest_ref=latest_ref,
            latest_url=release.get("html_url"),
            changes=str(release.get("body") or "No release notes were provided."),
            update_available=_is_newer(latest_version, installed),
            source="github_release",
        )
    except HTTPError as exc:
        if exc.code != 404:
            return _error_info(installed, str(exc))
    except (URLError, OSError, TimeoutError) as exc:
        return _error_info(installed, str(exc))

    try:
        tags = _fetch_json(
            f"{GITHUB_API_ROOT}/tags",
            timeout=timeout,
            urlopen_factory=urlopen_factory,
        )
        latest_tag = tags[0] if tags else {}
        latest_ref = str(latest_tag.get("name") or "").strip() or None
        latest_version = _normalize_version(latest_ref)
        return UpdateInfo(
            current_version=installed,
            latest_version=latest_version,
            latest_ref=latest_ref,
            latest_url=latest_tag.get("zipball_url"),
            changes="No release notes were found for this tag.",
            update_available=_is_newer(latest_version, installed),
            source="github_tags",
        )
    except (HTTPError, URLError, OSError, TimeoutError, IndexError) as exc:
        return _error_info(installed, str(exc))


def _fetch_json(
    url: str,
    *,
    timeout: float,
    urlopen_factory: Callable[..., Any],
) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ros2unbag-update-checker",
        },
    )
    with urlopen_factory(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _error_info(current: str, error: str) -> UpdateInfo:
    return UpdateInfo(
        current_version=current,
        latest_version=None,
        latest_ref=None,
        latest_url=None,
        changes="",
        update_available=False,
        source="error",
        error=error,
    )


def _normalize_version(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    return value[1:] if value.lower().startswith("v") else value


def _is_newer(latest: str | None, current: str) -> bool:
    if latest is None or current == "unknown":
        return False
    return _version_key(latest) > _version_key(current)


def _version_key(value: str) -> tuple[int, ...]:
    cleaned = _normalize_version(value) or value
    numeric_parts: list[int] = []
    for part in cleaned.replace("-", ".").split("."):
        digits = "".join(character for character in part if character.isdigit())
        if not digits:
            break
        numeric_parts.append(int(digits))
    return tuple(numeric_parts or [0])
