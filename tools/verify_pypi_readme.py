"""Verify the README that PyPI will render, including its remote release assets."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from readme_renderer.markdown import render

from tools.verify_public_distribution import (
    ASSET_COMMIT,
    EXPECTED_PROGRAMMER_GUIDE,
    EXPECTED_PROGRAMMER_GUIDE_URL,
    EXPECTED_SCREENSHOT,
    EXPECTED_SCREENSHOT_URL,
)


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "PyCForge-release-verifier/0.15.2"


class PyPIReadmeVerificationError(RuntimeError):
    """The rendered PyPI README or one of its public assets is invalid."""


class _AssetCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.image_sources: list[str] = []
        self.link_targets: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if tag == "img" and values.get("src") is not None:
            self.image_sources.append(values["src"] or "")
        elif tag == "a" and values.get("href") is not None:
            self.link_targets.append(values["href"] or "")


def _render_and_verify() -> dict[str, object]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    rendered = render(readme)
    if rendered is None:
        raise PyPIReadmeVerificationError("PyPI Markdown rendering failed")
    collector = _AssetCollector()
    collector.feed(rendered)
    if collector.image_sources.count(EXPECTED_SCREENSHOT_URL) != 1:
        raise PyPIReadmeVerificationError(
            "rendered PyPI README does not contain the exact screenshot"
        )
    if collector.link_targets.count(EXPECTED_PROGRAMMER_GUIDE_URL) != 2:
        raise PyPIReadmeVerificationError(
            "rendered PyPI README does not contain both programmer-guide links"
        )
    return {
        "rendered_html_bytes": len(rendered.encode("utf-8")),
        "screenshot_elements": 1,
        "programmer_guide_links": 2,
    }


def _open(url: str):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    return urlopen(request, timeout=30)


def _download_exact(url: str, expected_path: Path) -> int:
    expected = expected_path.read_bytes()
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with _open(url) as response:
                payload = response.read(len(expected) + 1)
            if payload != expected:
                raise PyPIReadmeVerificationError(
                    f"remote asset differs from {expected_path.relative_to(ROOT)}"
                )
            return len(payload)
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise PyPIReadmeVerificationError(
        f"remote asset did not resolve after three attempts: {url}"
    ) from last_error


def verify() -> dict[str, object]:
    report = _render_and_verify()
    report["screenshot_bytes"] = _download_exact(
        EXPECTED_SCREENSHOT_URL, ROOT / EXPECTED_SCREENSHOT
    )
    report["programmer_guide_bytes"] = _download_exact(
        EXPECTED_PROGRAMMER_GUIDE_URL, ROOT / EXPECTED_PROGRAMMER_GUIDE
    )
    report["asset_commit"] = ASSET_COMMIT
    return report


def main() -> int:
    try:
        report = verify()
    except (OSError, PyPIReadmeVerificationError, ValueError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"passed": True, **report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
