#!/usr/bin/env python3
"""List external origins referenced by the frontend and flag ones the CSP never allows.

Sources of truth:
  * the policy in frontend/nginx.conf (see extract_policy.py)
  * every external https:// host that appears in the built JS/CSS

A host that no directive allows is a CSP violation waiting to happen the moment the
code path that fetches it runs. A host that IS allowed somewhere may still violate on
the specific directive that loads it (a style pulled from a script-src-only host, say)
-- run the browser probe from SKILL.md to settle that.

Bare --dist resolves this repo's frontend/build from any directory; pass a path only for
a build elsewhere, and note it is relative to your shell, not to this script:

    python3 scan_origins.py --dist                                 # after `bun run build`
    python3 scan_origins.py --url https://us-central.unstract.com
    python3 scan_origins.py --dist /tmp/other-build --conf /tmp/other-nginx.conf

Exit non-zero on anything that means "this scan did not actually check the policy": a
host in no fetch directive, a path or port outside what its sources allow, a --dist that
is missing or holds no .js, a URL whose index names no bundle, or a failure fetching a
chunk index.html links. A 404 on a path found only inside a bundle string is tolerated --
that is usually a worker path a chunk names but never loads. A scan that inspected
nothing must never look like a pass.
"""

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from extract_policy import DEFAULT_CONF, parse

URL_RE = re.compile(
    r"https://([a-zA-Z0-9][a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})(:\d+)?(/[^\s\"'`)\\<>]*)?"
)

# Directives that govern navigation or reporting rather than loading a subresource. A
# host listed in one of them cannot be fetched on its strength, so letting it into the
# allowed map would clear references the browser blocks.
NON_FETCH_DIRECTIVES = {
    "form-action",
    "base-uri",
    "frame-ancestors",
    "report-uri",
    "report-to",
    "sandbox",
}
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
    # index.html alone is not a build. Without this, an interrupted or wrong-directory
    # build scans one file, finds no external host in it, and reads as a pass.
    if not any(name.endswith(".js") for name in files):
        raise SystemExit(f"--dist {dist} holds no .js bundle -- nothing to check")
    return files


def fetch(url: str, attempts: int = 3) -> str:
    """One transient TLS or connection error should not redden the whole gate."""
    for attempt in range(1, attempts + 1):
        try:
            return (
                urllib.request.urlopen(url, timeout=20).read().decode("utf-8", "ignore")
            )
        except urllib.error.HTTPError:
            raise  # a status code is an answer, not a blip
        except Exception:  # noqa: BLE001 - retry, then let the caller record it
            if attempt == attempts:
                raise
            time.sleep(attempt)
    raise AssertionError("unreachable")


def read_deployment(base_url: str) -> tuple[dict[str, str], list[str]]:
    """Return ({name: body}, [failed paths]). The caller must fail on the failures:
    an auth wall or a CDN 403 empties the scan, and an empty scan finds no gaps.
    """
    base_url = base_url.rstrip("/")
    try:
        index = fetch(base_url + "/")
    except Exception as exc:  # noqa: BLE001 - report it as an incomplete scan, not a traceback
        raise SystemExit(f"could not fetch {base_url}/ : {exc}") from exc
    # index.html and the entrypoint-generated runtime config carry origins of their own
    # (the operator-set logo and favicon URLs), and neither is under /assets/.
    files = {"index.html": index}
    failures: list[str] = []
    # A chunk index.html links is real code and has to be there; one found by following
    # RELATIVE_ASSET_RE inside a bundle may be a path the chunk only names as a string (a
    # worker it never loads), so its absence proves nothing. Required-ness is kept in a
    # dict, not carried on the queue: the same path can arrive from both sources, and
    # whichever entry happens to be popped first must not decide how a 404 is treated.
    required_by_path = {path: True for path in ASSET_RE.findall(index)}
    if not required_by_path:
        # A login wall or a redirect serves a perfectly good 200 with no bundle in it.
        raise SystemExit(f"{base_url}/ references no /assets/ chunk -- not the SPA?")
    required_by_path.setdefault("/config/runtime-config.js", False)
    queue = list(required_by_path)
    seen = set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        required = required_by_path[path]
        try:
            body = fetch(base_url + path)
        except urllib.error.HTTPError as exc:
            # A 404 is only tolerable on a speculative path. Anything else -- an auth
            # wall, a CDN 403, a 5xx, or any failure on a chunk index.html links --
            # means the scan is missing real code and cannot clear the policy.
            print(f"  ! {path}: {exc}", file=sys.stderr)
            if required or exc.code != 404:
                failures.append(f"{path} ({exc.code})")
            continue
        except Exception as exc:  # noqa: BLE001 - keep scanning, but record the gap
            print(f"  ! {path}: {exc}", file=sys.stderr)
            failures.append(f"{path} ({exc})")
            continue
        files[path.split("/")[-1]] = body
        for match in RELATIVE_ASSET_RE.findall(body):
            discovered = "/assets/" + match[2:]
            required_by_path.setdefault(discovered, False)
            queue.append(discovered)
    return files, failures


def allowed_sources(directives: dict[str, list[str]]) -> dict[str, set[tuple[str, str]]]:
    """{host pattern: {(port, path prefix)}}. An empty prefix means the whole host.

    `https://www.google.com/recaptcha/` grants exactly that path, not the host -- keeping
    the prefix is what stops the scanner reporting `https://www.google.com/g/collect` as
    covered when the browser would block it. A source with no port grants the default
    port only, which is why the port is kept alongside.
    """
    hosts: dict[str, set[tuple[str, str]]] = {}
    for directive, sources in directives.items():
        if directive in NON_FETCH_DIRECTIVES:
            continue
        for source in sources:
            if not source.startswith("https://"):
                continue
            authority, _, path = source[len("https://") :].partition("/")
            host, _, port = authority.partition(":")
            hosts.setdefault(host, set()).add((port or "443", "/" + path if path else ""))
    return hosts


def host_matches(ref_host: str, pattern: str) -> bool:
    # CSP wildcards cover subdomains only: *.example.com does not match example.com.
    if pattern.startswith("*."):
        return ref_host.endswith(pattern[1:])
    return ref_host == pattern


def verdict(
    host: str, port: str, paths: set[str], allowed: dict[str, set[tuple[str, str]]]
) -> tuple[str, str]:
    """('allowed'|'PATH'|'PORT'|'MISSING', the detail that fails)."""
    entries: set[tuple[str, str]] = set()
    for pattern, pattern_entries in allowed.items():
        if host_matches(host, pattern):
            entries |= pattern_entries
    if not entries:
        return "MISSING", ""
    prefixes = {prefix for src_port, prefix in entries if src_port in (port, "*")}
    if not prefixes:
        return "PORT", f":{port}"
    if "" in prefixes:
        return "allowed", ""
    for path in sorted(paths):
        if not any(path.startswith(prefix) for prefix in prefixes):
            return "PATH", path or "/"
    return "allowed", ""


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dist",
        type=Path,
        nargs="?",
        const=DEFAULT_CONF.parent / "build",
        help="built frontend directory (default: the repo's frontend/build)",
    )
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

    found: dict[tuple[str, str], dict[str, set[str]]] = {}
    for name, body in files.items():
        for host, port, path in URL_RE.findall(body):
            if host in IGNORED:
                continue
            key = (host, port.lstrip(":") or "443")
            entry = found.setdefault(key, {"files": set(), "paths": set()})
            entry["files"].add(name)
            entry["paths"].add(path)

    problems: list[str] = []
    for host, port in sorted(found):
        mark, detail = verdict(host, port, found[(host, port)]["paths"], allowed)
        label = host if port == "443" else f"{host}:{port}"
        chunks = ", ".join(sorted(found[(host, port)]["files"])[:3])
        suffix = f"  <- {detail}" if detail else ""
        print(f"  {mark:8} {label:38} {chunks}{suffix}")
        if mark == "MISSING":
            problems.append(f"{label} is in no fetch directive")
        elif mark == "PORT":
            problems.append(f"{label} is on a port no source for {host} allows")
        elif mark == "PATH":
            problems.append(f"{host}{detail} is outside the allowed path on {host}")

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
