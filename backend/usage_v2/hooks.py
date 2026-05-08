"""Post-write hooks for ``UsageBatchCreateView``.

Hooks fire inside the view's transaction; a failure rolls the batch back
so Usage rows and any side-table writes stay consistent. Records carry
an opaque ``cloud_extras`` dict that OSS forwards verbatim — plugins
read only the keys they own.
"""

from collections.abc import Callable

from .models import Usage

PostWriteHook = Callable[[list[dict], list[Usage]], None]

_post_write_hooks: list[PostWriteHook] = []


def register_post_write_hook(fn: PostWriteHook) -> PostWriteHook:
    # Idempotent: ready() can re-fire under test reloads / dev autoreload.
    if fn not in _post_write_hooks:
        _post_write_hooks.append(fn)
    return fn


def run_post_write_hooks(records: list[dict], usage_objects: list[Usage]) -> None:
    for hook in _post_write_hooks:
        hook(records, usage_objects)
