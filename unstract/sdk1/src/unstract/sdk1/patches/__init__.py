"""Monkey-patches for third-party library bugs.

Patches in this package are applied via side-effect imports.
Currently activated from unstract.sdk1.embedding — any code path
that reaches Bedrock Cohere embeddings without going through that
module will NOT have patches active.
"""
