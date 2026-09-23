"""Helpers shared between test modules in different Django apps.

Kept out of any one app because its consumers span several
(``api_v2``, ``prompt_studio``); ``permissions/tests/base.py`` is the
app-scoped equivalent for helpers with a single consumer.
"""
