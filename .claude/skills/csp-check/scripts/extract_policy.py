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
    """Return (header_name, {directive: [sources]}) for the conf's CSP header."""
    text = conf_path.read_text()
    match = HEADER_RE.search(text)
    if not match:
        raise SystemExit(f"No Content-Security-Policy add_header found in {conf_path}")
    header = match.group(1)
    directives = {}
    for chunk in match.group("policy").split(";"):
        parts = chunk.split()
        if parts:
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
