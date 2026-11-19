"""`AGENT_KV_PATH_PREFIX` is whitelisted out of authentication, so it is input.

The execution API authenticates in its views, which means its prefix is added
to `WHITELISTED_PATHS` and `CustomAuthMiddleware` skips anything matching it —
by `startswith`, not by equality. That makes the value security-relevant in a
way an env var normally is not:

* empty or whitespace-only produces the entry `/`, a prefix of **every** path
  on the service, so nothing is authenticated at all;
* a value that collides with another mounted prefix (`api`, `api/v1`,
  `deployment`) exempts that whole surface instead.

Both are operator mistakes rather than attacks, and both are silent — the
server starts, every request succeeds, and no log line says the API is now
open. Reported by @athul-rs on #2317.
"""

import os

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

from backend.settings.base import validate_agent_kv_path_prefix  # noqa: E402

_PATH = "api/v1"
_DEPLOY = "deployment"


def _validate(raw):
    return validate_agent_kv_path_prefix(raw, _PATH, _DEPLOY)


@pytest.mark.parametrize("raw", ["", "   ", "/", "//", None])
def test_an_empty_prefix_is_refused(raw):
    """`/` matches every path. This is the one that turns the whole service
    anonymous, so it must not be reachable by leaving a value blank.
    """
    with pytest.raises(ImproperlyConfigured, match="must not be empty"):
        _validate(raw)


@pytest.mark.parametrize("raw", ["api", "api/v1", "deployment", "/api/", "api/v1/"])
def test_a_prefix_that_swallows_another_surface_is_refused(raw):
    """Equal to, or an ancestor of, a prefix that is NOT whitelisted. `api`
    exempts `/api/v1/...`, i.e. the entire tenant API including key
    management.
    """
    with pytest.raises(ImproperlyConfigured, match="collides with"):
        _validate(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("agent-kv", "agent-kv"),
        ("/agent-kv/", "agent-kv"),
        ("  agent-kv  ", "agent-kv"),
        ("agent-kv/v2", "agent-kv/v2"),
        # A DESCENDANT of another prefix is fine: `/api/v1/...` does not start
        # with `/api/v1/unstract/agent-kv`, so nothing extra is exempted.
        ("api/v1/unstract/agent-kv", "api/v1/unstract/agent-kv"),
        # Shares a textual prefix with `deployment` but is not an ancestor of
        # it, so it exempts only itself.
        ("deploy", "deploy"),
    ],
)
def test_a_safe_prefix_is_accepted_and_normalised(raw, expected):
    assert _validate(raw) == expected


def test_the_default_is_safe():
    """Guards the guard: every refusal above would still pass if the shipped
    default were itself rejected, and nobody would notice until deploy.
    """
    from django.conf import settings

    assert settings.AGENT_KV_PATH_PREFIX == "api/v1/agentic-extract"
    assert f"/{settings.AGENT_KV_PATH_PREFIX}" in settings.WHITELISTED_PATHS


def test_the_env_samples_ship_the_shipped_default():
    """Both `sample.env` files set this key as an ACTIVE assignment, so what
    they say is what a deployment set up the documented way actually serves --
    the default above is not.

    Without this, reverting one sample file and nothing else passes the whole
    suite, and those deployments keep serving the old path while the docs
    (guarded by `test_docs_examples.py`) show the new one. That is the
    integrator-facing failure one hop out from the one that guard prevents.

    `docker/sample.env` is also read at runtime by
    `workers/tests/test_queue_consumer_wiring.py`, which derives the traefik
    term it checks from it rather than restating the prefix.
    """
    import pathlib

    from django.conf import settings

    root = pathlib.Path(__file__).resolve().parents[3]
    for sample in (root / "backend" / "sample.env", root / "docker" / "sample.env"):
        assigned = [
            line.split("=", 1)[1].split("#")[0].strip()
            for line in sample.read_text().splitlines()
            if line.startswith("AGENT_KV_PATH_PREFIX=")
        ]
        assert assigned == [settings.AGENT_KV_PATH_PREFIX], (
            f"{sample.parent.name}/{sample.name} sets AGENT_KV_PATH_PREFIX to "
            f"{assigned!r}, but the shipped default is "
            f"{settings.AGENT_KV_PATH_PREFIX!r}. A deployment built from this "
            "sample serves the sample's value, not the default."
        )
