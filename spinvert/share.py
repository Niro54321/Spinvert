"""Share a screenshot as a link, like Lightshot: the picture goes to a Spinvert
share server (the Cloudflare Worker in server/) and comes back as a link
nobody can guess. Nothing is uploaded unless the user presses Share link."""

from __future__ import annotations

import html
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from spinvert import __version__
from spinvert.util import app_data_dir

# The public server run for everyone who uses Spinvert; Settings can name another.
DEFAULT_SERVER = ""


class ShareError(Exception):
    pass


def server_for(settings) -> str:
    return (settings.share_server.strip() or DEFAULT_SERVER).rstrip("/")


def valid_server(url: str) -> bool:
    """https only, except a server running on this PC (for testing your own)."""
    parts = urlsplit(url)
    return bool(parts.netloc) and (parts.scheme == "https" or
                                   (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")))


def upload(png: bytes, server: str, timeout: float = 60) -> dict:
    """The links for a PNG: {url, image, delete, expires}. Raises ShareError."""
    if not valid_server(server):
        raise ShareError("The share server address must start with https://.")
    request = urllib.request.Request(f"{server}/upload", data=png, method="POST", headers={
        "Content-Type": "image/png", "User-Agent": f"Spinvert/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read()).get("error")
        except ValueError:
            message = None
        raise ShareError(message or f"The share server answered with error {e.code}.") from None
    except (OSError, ValueError):  # no connection, timeout, or not JSON
        raise ShareError("Couldn't reach the share server. Check your internet connection.") from None
    if not all(str(result.get(k, "")).startswith(server + "/") for k in ("url", "image", "delete")):
        raise ShareError("The share server sent back something unexpected.")
    remember(result)
    return result


# history: every link with its delete link, so a picture can be taken down later

def history_file():
    return app_data_dir() / "shared.json"


def history_page():
    return app_data_dir() / "Shared links.html"


def history() -> list[dict]:
    try:
        items = json.loads(history_file().read_text(encoding="utf-8"))
        return items if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def remember(result: dict) -> None:
    items = history()
    items.append({"url": result["url"], "delete": result["delete"], "expires": result.get("expires", ""),
                  "shared": time.strftime("%Y-%m-%d %H:%M")})
    try:
        history_file().write_text(json.dumps(items, indent=2), encoding="utf-8")
        write_page(items)
    except OSError:
        pass  # the link still works; only the list of links is missing it


def write_page(items: list[dict]) -> None:
    rows = "\n".join(
        f"<tr><td>{html.escape(i.get('shared', ''))}</td>"
        f"<td><a href=\"{html.escape(i['url'])}\">{html.escape(i['url'])}</a></td>"
        f"<td>{html.escape(i.get('expires', ''))}</td>"
        f"<td><a class=\"del\" href=\"{html.escape(i['delete'])}\">Delete…</a></td></tr>"
        for i in reversed(items))
    history_page().write_text(f"""<!doctype html><meta charset="utf-8"><title>Spinvert: shared links</title>
<style>body{{font:15px "Segoe UI",sans-serif;margin:32px;background:#111318;color:#eee}}
table{{border-collapse:collapse}}td,th{{padding:8px 14px;border-bottom:1px solid #333;text-align:left}}
a{{color:#b9a8ff}}.del{{color:#ff8fa3}}</style>
<h2>Screenshots you shared</h2>
<p>Anyone with a link can see that picture. Open <b>Delete…</b> to take one down for everyone.</p>
<table><tr><th>Shared</th><th>Link</th><th>Deleted on</th><th></th></tr>
{rows}
</table>""", encoding="utf-8")
