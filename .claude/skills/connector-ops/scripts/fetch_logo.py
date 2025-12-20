#!/usr/bin/env python3
"""
Fetch connector logo from various sources.

Usage:
    python fetch_logo.py "service_name" "output_path"

Example:
    python fetch_logo.py "PostgreSQL" "/path/to/frontend/public/icons/connector-icons/Postgresql.png"

Sources tried in order:
1. SimpleIcons (simpleicons.org)
2. Devicon (devicon.dev)
3. Logo.dev API
4. Web search fallback
5. Skip if not found
"""

import sys
import os
import re
import urllib.request
import urllib.error
import json
from pathlib import Path


def normalize_name(name: str) -> str:
    """Normalize service name for API lookups."""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def fetch_simple_icons(name: str, output_path: str) -> bool:
    """Try to fetch from SimpleIcons CDN."""
    normalized = normalize_name(name)

    # SimpleIcons provides SVGs, we'll save as-is
    url = f"https://cdn.simpleicons.org/{normalized}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                content = response.read()
                # Save as SVG if output expects PNG, note this
                svg_path = output_path.rsplit('.', 1)[0] + '.svg'
                with open(svg_path, 'wb') as f:
                    f.write(content)
                print(f"[SimpleIcons] Logo saved to: {svg_path}")
                return True
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"[SimpleIcons] Not found: {e}")

    return False


def fetch_devicon(name: str, output_path: str) -> bool:
    """Try to fetch from Devicon CDN."""
    normalized = normalize_name(name)

    # Devicon URL patterns
    variants = [
        f"https://cdn.jsdelivr.net/gh/devicons/devicon/icons/{normalized}/{normalized}-original.svg",
        f"https://cdn.jsdelivr.net/gh/devicons/devicon/icons/{normalized}/{normalized}-plain.svg",
        f"https://cdn.jsdelivr.net/gh/devicons/devicon/icons/{normalized}/{normalized}-original-wordmark.svg",
    ]

    for url in variants:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    content = response.read()
                    svg_path = output_path.rsplit('.', 1)[0] + '.svg'
                    with open(svg_path, 'wb') as f:
                        f.write(content)
                    print(f"[Devicon] Logo saved to: {svg_path}")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError):
            continue

    print("[Devicon] Not found")
    return False


def fetch_logo_dev(name: str, output_path: str) -> bool:
    """Try to fetch from logo.dev API."""
    # logo.dev uses domain names
    domain_guesses = [
        f"{normalize_name(name)}.com",
        f"{normalize_name(name)}.io",
        f"{normalize_name(name)}.org",
    ]

    for domain in domain_guesses:
        url = f"https://img.logo.dev/{domain}?token=pk_anonymous"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    content = response.read()
                    # logo.dev returns PNG
                    with open(output_path, 'wb') as f:
                        f.write(content)
                    print(f"[logo.dev] Logo saved to: {output_path}")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError):
            continue

    print("[logo.dev] Not found")
    return False


def fetch_clearbit(name: str, output_path: str) -> bool:
    """Try to fetch from Clearbit Logo API."""
    domain_guesses = [
        f"{normalize_name(name)}.com",
        f"{normalize_name(name)}.io",
        f"{normalize_name(name)}.org",
    ]

    for domain in domain_guesses:
        url = f"https://logo.clearbit.com/{domain}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    content = response.read()
                    with open(output_path, 'wb') as f:
                        f.write(content)
                    print(f"[Clearbit] Logo saved to: {output_path}")
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError):
            continue

    print("[Clearbit] Not found")
    return False


def main():
    if len(sys.argv) != 3:
        print("Usage: python fetch_logo.py <service_name> <output_path>")
        print("Example: python fetch_logo.py PostgreSQL ./Postgresql.png")
        sys.exit(1)

    service_name = sys.argv[1]
    output_path = sys.argv[2]

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"Fetching logo for: {service_name}")
    print(f"Output path: {output_path}")
    print("-" * 40)

    # Try sources in order
    sources = [
        ("SimpleIcons", fetch_simple_icons),
        ("Devicon", fetch_devicon),
        ("logo.dev", fetch_logo_dev),
        ("Clearbit", fetch_clearbit),
    ]

    for source_name, fetch_func in sources:
        print(f"Trying {source_name}...")
        if fetch_func(service_name, output_path):
            print("-" * 40)
            print(f"SUCCESS: Logo fetched from {source_name}")
            sys.exit(0)

    print("-" * 40)
    print("WARNING: Could not fetch logo from any source.")
    print("Please manually add a logo to:")
    print(f"  {output_path}")
    print("\nSuggested sources:")
    print(f"  - Official {service_name} brand/press page")
    print("  - Wikipedia (check licensing)")
    print("  - Create a simple text-based placeholder")
    sys.exit(1)


if __name__ == "__main__":
    main()
