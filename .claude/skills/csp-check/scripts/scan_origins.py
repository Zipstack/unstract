#!/usr/bin/env python3
"""List external origins referenced by the frontend and flag ones the CSP never allows.

Sources of truth:
  * the policy in frontend/nginx.conf (see extract_policy.py)
  * every external https:// host that appears in the built JS/CSS

A host that no directive allows is a CSP violation waiting to happen the moment the
code path that fetches it runs. A host that IS allowed somewhere may still violate on
the specific directive that loads it (a style pulled from a script-src-only host, say)
-- run the browser probe from SKILL.md to settle that.

Usage:
    python3 scan_origins.py --dist frontend/dist          # after `npm run build`
    python3 scan_origins.py --url https://us-central.unstract.com
    python3 scan_origins.py --dist frontend/dist --conf frontend/nginx.conf
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

from extract_policy import DEFAULT_CONF, parse

URL_RE = re.compile(r"https://([a-zA-Z0-9][a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})")
ASSET_RE = re.compile(r"/assets/[A-Za-z0-9_%.\-]+\.(?:js|css)")
RELATIVE_ASSET_RE = re.compile(r"[\"'(](\./[A-Za-z0-9_%.\-]+\.(?:js|css))")

# Hosts that only ever appear as documentation links, XML namespaces or library
# error strings -- they are never fetched, so they need no CSP entry.
IGNORED = {
    "www.w3.org",
    "json-schema.org",
    "momentjs.com",
    "github.com",
    "raw.githubusercontent.com",
    "reactjs.org",
    "redux.js.org",
    "redux-toolkit.js.org",
    "react-dnd.github.io",
    "handlebarsjs.com",
    "socket.io",
    "npms.io",
    "example.com",
    "bit.ly",
    "fb.me",
    "yandex.com",
    "sentry.io",
    "posthog.com",
    "app.posthog.com",
    "us.posthog.com",
    "us.i.posthog.com",
    "us-assets.i.posthog.com",
    "docs.unstract.com",
    "join-slack.unstract.com",
    "billing.stripe.com",
    "checkout.stripe.com",
    "fonts.google.com",
}


def read_dist(dist: Path) -> dict[str, str]:
    files = {}
    for path in list(dist.rglob("*.js")) + list(dist.rglob("*.css")):
        files[path.name] = path.read_text(encoding="utf-8", errors="ignore")
    return files


def read_deployment(base_url: str) -> dict[str, str]:
    base_url = base_url.rstrip("/")
    index = urllib.request.urlopen(base_url + "/").read().decode("utf-8", "ignore")
    queue = list(dict.fromkeys(ASSET_RE.findall(index)))
    files, seen = {}, set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            body = (
                urllib.request.urlopen(base_url + path).read().decode("utf-8", "ignore")
            )
        except Exception as exc:  # noqa: BLE001 - a 404 chunk should not abort the scan
            print(f"  ! {path}: {exc}", file=sys.stderr)
            continue
        files[path.split("/")[-1]] = body
        queue.extend("/assets/" + m[2:] for m in RELATIVE_ASSET_RE.findall(body))
    return files


def allowed_hosts(directives: dict[str, list[str]]) -> set[str]:
    hosts = set()
    for sources in directives.values():
        for source in sources:
            if source.startswith("https://"):
                hosts.add(source[len("https://") :].split("/")[0])
    return hosts


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dist", type=Path, help="built frontend directory")
    group.add_argument("--url", help="deployment base URL")
    parser.add_argument("--conf", type=Path, default=DEFAULT_CONF)
    args = parser.parse_args()

    header, directives = parse(args.conf)
    allowed = allowed_hosts(directives)
    files = read_dist(args.dist) if args.dist else read_deployment(args.url)
    print(f"Scanned {len(files)} bundle files against {header} in {args.conf}\n")

    found: dict[str, set[str]] = {}
    for name, body in files.items():
        for host in URL_RE.findall(body):
            if host not in IGNORED:
                found.setdefault(host, set()).add(name)

    uncovered = {h: f for h, f in found.items() if h not in allowed}
    for host in sorted(found):
        mark = "MISSING " if host in uncovered else "allowed "
        chunks = ", ".join(sorted(found[host])[:3])
        print(f"  {mark} {host:38} {chunks}")

    if uncovered:
        print(f"\n{len(uncovered)} host(s) referenced by the bundle are in no directive.")
        print("Add them to the directive that loads them in frontend/nginx.conf.")
        sys.exit(1)
    print("\nEvery external host referenced by the bundle appears in the policy.")


if __name__ == "__main__":
    main()
