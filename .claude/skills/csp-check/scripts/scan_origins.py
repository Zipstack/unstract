#!/usr/bin/env python3
"""List external origins referenced by the frontend and flag ones the CSP never allows.

Sources of truth:
  * the policy in frontend/nginx.conf (see extract_policy.py)
  * every external https:// host that appears in the built JS/CSS

A host that no directive allows is a CSP violation waiting to happen the moment the
code path that fetches it runs. A host that IS allowed somewhere may still violate on
the specific directive that loads it (a style pulled from a script-src-only host, say)
-- run the browser probe from SKILL.md to settle that.

Paths are relative to the working directory, so from this script's own directory the
build is four levels up:

    python3 scan_origins.py --dist ../../../../frontend/build      # after `bun run build`
    python3 scan_origins.py --url https://us-central.unstract.com
    python3 scan_origins.py --dist ../../../../frontend/build --conf ../../../../frontend/nginx.conf

Exit non-zero on anything that means "this scan did not actually check the policy":
a host in no directive, a path outside a path-scoped source, a --dist that is missing or
holds no bundle files, a URL whose index references no bundle at all, or a chunk that
failed to fetch for any reason but a 404. A scan that inspected nothing must never look
like a pass.
"""

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from extract_policy import DEFAULT_CONF, parse

URL_RE = re.compile(
    r"https://([a-zA-Z0-9][a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})(/[^\s\"'`)\\<>]*)?"
)
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
    "react.dev",
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
    # rglob on a missing directory yields nothing instead of raising, which would turn a
    # mistyped --dist into a clean pass over zero files.
    if not dist.is_dir():
        raise SystemExit(f"--dist {dist} is not a directory (cwd: {Path.cwd()})")
    files = {}
    for pattern in ("*.js", "*.css", "*.html"):
        for path in dist.rglob(pattern):
            files[str(path.relative_to(dist))] = path.read_text(
                encoding="utf-8", errors="ignore"
            )
    return files


def read_deployment(base_url: str) -> tuple[dict[str, str], list[str]]:
    """Return ({name: body}, [failed paths]). The caller must fail on the failures:
    an auth wall or a CDN 403 empties the scan, and an empty scan finds no gaps.
    """
    base_url = base_url.rstrip("/")
    index = urllib.request.urlopen(base_url + "/").read().decode("utf-8", "ignore")
    # index.html and the entrypoint-generated runtime config carry origins of their own
    # (the operator-set logo and favicon URLs), and neither is under /assets/.
    files = {"index.html": index}
    failures: list[str] = []
    queue = list(dict.fromkeys(ASSET_RE.findall(index)))
    if not queue:
        # A login wall or a redirect serves a perfectly good 200 with no bundle in it.
        raise SystemExit(f"{base_url}/ references no /assets/ chunk -- not the SPA?")
    queue.append("/config/runtime-config.js")
    seen = set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            body = (
                urllib.request.urlopen(base_url + path).read().decode("utf-8", "ignore")
            )
        except urllib.error.HTTPError as exc:
            # RELATIVE_ASSET_RE also matches worker paths a chunk merely names as a
            # string, so a 404 here is usually a path that was never a chunk. Anything
            # else (an auth wall, a CDN 403, a 5xx) means the scan is missing real code.
            print(f"  ! {path}: {exc}", file=sys.stderr)
            if exc.code != 404:
                failures.append(f"{path} ({exc.code})")
            continue
        except Exception as exc:  # noqa: BLE001 - keep scanning, but record the gap
            print(f"  ! {path}: {exc}", file=sys.stderr)
            failures.append(f"{path} ({exc})")
            continue
        files[path.split("/")[-1]] = body
        queue.extend("/assets/" + m[2:] for m in RELATIVE_ASSET_RE.findall(body))
    return files, failures


def allowed_sources(directives: dict[str, list[str]]) -> dict[str, set[str]]:
    """{host pattern: path prefixes}. An empty prefix means the whole host is allowed.

    `https://www.google.com/recaptcha/` grants exactly that path, not the host -- keeping
    the prefix is what stops the scanner reporting `https://www.google.com/g/collect` as
    covered when the browser would block it.
    """
    hosts: dict[str, set[str]] = {}
    for sources in directives.values():
        for source in sources:
            if not source.startswith("https://"):
                continue
            host, _, path = source[len("https://") :].partition("/")
            hosts.setdefault(host, set()).add("/" + path if path else "")
    return hosts


def host_matches(ref_host: str, pattern: str) -> bool:
    # CSP wildcards cover subdomains only: *.example.com does not match example.com.
    if pattern.startswith("*."):
        return ref_host.endswith(pattern[1:])
    return ref_host == pattern


def verdict(host: str, paths: set[str], allowed: dict[str, set[str]]) -> tuple[str, str]:
    """('allowed'|'PATH'|'MISSING', offending path)."""
    prefixes: set[str] = set()
    for pattern, pattern_prefixes in allowed.items():
        if host_matches(host, pattern):
            prefixes |= pattern_prefixes
    if not prefixes:
        return "MISSING", ""
    if "" in prefixes:
        return "allowed", ""
    for path in sorted(paths):
        if not any(path.startswith(prefix) for prefix in prefixes):
            return "PATH", path or "/"
    return "allowed", ""


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dist", type=Path, help="built frontend directory")
    group.add_argument("--url", help="deployment base URL")
    parser.add_argument("--conf", type=Path, default=DEFAULT_CONF)
    args = parser.parse_args()

    header, directives = parse(args.conf)
    allowed = allowed_sources(directives)
    if args.dist:
        files, failures = read_dist(args.dist), []
    else:
        files, failures = read_deployment(args.url)
    print(f"Scanned {len(files)} bundle files against {header} in {args.conf}\n")

    found: dict[str, dict[str, set[str]]] = {}
    for name, body in files.items():
        for host, path in URL_RE.findall(body):
            if host in IGNORED:
                continue
            entry = found.setdefault(host, {"files": set(), "paths": set()})
            entry["files"].add(name)
            entry["paths"].add(path)

    problems: list[str] = []
    for host in sorted(found):
        mark, path = verdict(host, found[host]["paths"], allowed)
        chunks = ", ".join(sorted(found[host]["files"])[:3])
        detail = f"  <- {path}" if path else ""
        print(f"  {mark:8} {host:38} {chunks}{detail}")
        if mark == "MISSING":
            problems.append(f"{host} is in no directive")
        elif mark == "PATH":
            problems.append(f"{host}{path} is outside the allowed path on {host}")

    if not files:
        raise SystemExit("\nScanned nothing -- an empty scan is not a pass.")
    if failures:
        print(f"\n{len(failures)} file(s) could not be fetched: {', '.join(failures)}")
        print("The scan is incomplete, so it cannot clear the policy.")
        sys.exit(1)
    if problems:
        print(f"\n{len(problems)} problem(s) the enforcing policy would block:")
        for problem in problems:
            print(f"  - {problem}")
        print("Add each to the directive that loads it in frontend/nginx.conf.")
        sys.exit(1)
    print("\nEvery external host referenced by the bundle appears in the policy.")


if __name__ == "__main__":
    main()
