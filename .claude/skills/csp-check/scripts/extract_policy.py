#!/usr/bin/env python3
"""Parse the Content-Security-Policy out of frontend/nginx.conf.

Usage:
    python3 extract_policy.py [path/to/nginx.conf]        # pretty-print per directive
    python3 extract_policy.py --json [path/to/nginx.conf] # machine-readable
"""

import json
import re
import sys
from pathlib import Path

HEADER_RE = re.compile(
    r'add_header\s+(Content-Security-Policy(?:-Report-Only)?)\s+"(?P<policy>[^"]*)"',
    re.IGNORECASE,
)
DEFAULT_CONF = Path(__file__).resolve().parents[4] / "frontend" / "nginx.conf"


def parse(conf_path: Path) -> tuple[str, dict[str, list[str]]]:
    """Return (header_name, {directive: [sources]}) for the conf's enforcing CSP header.

    Everything downstream trusts this as "what the browser sees", so it has to pick the
    same header the browser would: not a commented-out one, and not a -Report-Only
    header that happens to sit above the enforcing one (the usual shape while the next
    policy change is being trialled).
    """
    live = "\n".join(
        line
        for line in conf_path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )
    matches = HEADER_RE.findall(live)
    if not matches:
        raise SystemExit(f"No Content-Security-Policy add_header found in {conf_path}")
    enforcing = [m for m in matches if m[0].lower() == "content-security-policy"]
    chosen = enforcing or matches
    if len(chosen) > 1:
        names = ", ".join(name for name, _ in chosen)
        raise SystemExit(
            f"{conf_path} has {len(chosen)} CSP headers ({names}) -- ambiguous"
        )
    header, policy = chosen[0]
    directives: dict[str, list[str]] = {}
    for chunk in policy.split(";"):
        parts = chunk.split()
        if not parts:
            continue
        if parts[0] in directives:
            # The browser honours the first occurrence and ignores the rest, so keeping
            # the last would let the gate clear sources the browser never applies.
            print(
                f"warning: duplicate directive {parts[0]!r} in {conf_path}; "
                "the browser uses the first and ignores this one",
                file=sys.stderr,
            )
            continue
        directives[parts[0]] = parts[1:]
    return header, directives


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    conf = Path(args[0]) if args else DEFAULT_CONF
    header, directives = parse(conf)
    if as_json:
        print(json.dumps({"header": header, "directives": directives}, indent=2))
        return
    print(f"{header}  ({conf})")
    for directive, sources in directives.items():
        print(f"\n  {directive}")
        for source in sources:
            print(f"      {source}")


if __name__ == "__main__":
    main()
