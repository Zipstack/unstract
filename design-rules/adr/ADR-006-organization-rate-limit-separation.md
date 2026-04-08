# ADR-006: OrganizationRateLimit separated from Configuration

## Context

Per-organization configuration values are stored in `Configuration`. Rate limits could have been added as just another configuration row, but rate limits are not passive settings — they actively gate runtime behaviour and need their own update path, validation rules, and audit characteristics.

## Decision

`OrganizationRateLimit` is a separate model from `Configuration`. It lives in the `configuration` app but is not stored as a `Configuration` row.

## Consequences

- Rate limit changes have a dedicated change surface.
- `Configuration` remains a passive key-value store for settings that do not affect runtime gating.
- Future per-org gates that actively change behaviour should follow the same pattern: a dedicated model, not a `Configuration` row.
