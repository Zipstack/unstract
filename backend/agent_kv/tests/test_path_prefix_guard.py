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

import logging
import os
import re

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

from backend.settings.base import (  # noqa: E402
    RETIRED_AGENT_KV_PATH_PREFIX,
    validate_agent_kv_path_prefix,
)

#: The prefix this repo SHIPS, written once. Deliberately a literal rather
#: than `settings.AGENT_KV_PATH_PREFIX`, which is the *effective* value: the
#: setting is `os.environ.get`-derived and `base.py` loads `backend/.env`
#: before computing it, so on a checkout that pins the old prefix an
#: assertion against the setting blames whichever file is correct.
SHIPPED_DEFAULT = "api/v1/agentic-extract"

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

    assert settings.AGENT_KV_PATH_PREFIX == SHIPPED_DEFAULT
    assert f"/{settings.AGENT_KV_PATH_PREFIX}" in settings.WHITELISTED_PATHS


def test_the_env_samples_ship_the_shipped_default():
    """Both `sample.env` files set this key as an ACTIVE assignment, so
    `backend/sample.env`'s value -- not the code default -- is what a
    deployment set up the documented way actually serves. (`docker/sample.env`
    carries the key by convention only; nothing reads `docker/.env` into the
    backend. Its value still has to agree, or the two samples contradict each
    other.)

    Without this, reverting one sample file and nothing else passes the whole
    suite, and such a deployment keeps serving the old path while the docs
    (guarded by `test_docs_examples.py`) show the new one. That is the
    integrator-facing failure one hop out from the one that guard prevents.

    Compared against the literal, NOT against `settings`. The setting is
    `os.environ.get`-derived and `base.py` loads `backend/.env` before
    computing it, so on a checkout whose `.env` still pins the pre-rename value
    -- precisely the deployments the upgrade note exists for -- an assertion
    against `settings` fails on the *correct* file and names the sample as
    wrong. `test_the_default_is_safe` above is what ties this literal to the
    shipped default.

    `docker/sample.env` is also read at runtime by
    `workers/tests/test_queue_consumer_wiring.py`, which derives the traefik
    term it checks from it rather than restating the prefix.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    for sample in (root / "backend" / "sample.env", root / "docker" / "sample.env"):
        # Split the inline comment the way a dotenv parser does -- on WHITESPACE
        # followed by `#`, not on a bare `#`. `VALUE# comment` with no space is
        # not a comment at all: the whole remainder is the value. Padding this
        # block's comment column once produced exactly that, and a bare-`#`
        # split hid it, so the parse is part of what this test asserts.
        assigned = [
            re.split(r"\s#", line.split("=", 1)[1], maxsplit=1)[0].strip()
            for line in sample.read_text().splitlines()
            if line.startswith("AGENT_KV_PATH_PREFIX=")
        ]
        assert assigned == [SHIPPED_DEFAULT], (
            f"{sample.parent.name}/{sample.name} sets AGENT_KV_PATH_PREFIX to "
            f"{assigned!r}, but the shipped default is {SHIPPED_DEFAULT!r}. A "
            "deployment built from this sample serves the sample's value, not "
            "the default."
        )


def test_the_retired_prefix_is_accepted_but_warned_about(caplog):
    """Accepted, because the documented rollback is to set it back; warned
    about, because a deployment pinned to it serves a path the docs no longer
    describe and its callers get a 401 that blames their credential.

    This is the only notice that reaches every deployment type -- compose,
    on-prem and cloud -- without depending on which doc or sample file an
    operator reads. Everything else shipped for this rename is a static file on
    one deployment path.
    """
    with caplog.at_level(logging.WARNING):
        assert _validate(RETIRED_AGENT_KV_PATH_PREFIX) == RETIRED_AGENT_KV_PATH_PREFIX

    assert any(
        RETIRED_AGENT_KV_PATH_PREFIX in r.getMessage()
        and "agentic-extract" in r.getMessage()
        for r in caplog.records
    ), (
        "a deployment pinned to the retired prefix booted silently; the warning "
        f"must name both the retired value and the new one. Records: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


def test_the_shipped_default_warns_about_nothing(caplog):
    """Guards the guard: a warning that fires for every deployment is noise,
    and noise is how a real one gets filtered out.
    """
    with caplog.at_level(logging.WARNING):
        assert _validate(SHIPPED_DEFAULT) == SHIPPED_DEFAULT
    assert not caplog.records, [r.getMessage() for r in caplog.records]
