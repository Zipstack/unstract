# ADR-012: ConnectorAuth is owned by User

## Context

A `ConnectorAuth` row stores the OAuth tokens or credentials a person used to log into a third-party service (Google Drive, Box, etc.). The token represents the *individual's* identity at that third party, not the organization's. If `ConnectorAuth` were owned by an organization-membership row, transferring or removing the membership would orphan the token in unintuitive ways.

## Decision

`ConnectorAuth` has a FK to `User`, with `on_delete=CASCADE`. Deleting the user removes their connector auth records. The token's lifecycle is tied to the person, not their org membership.

## Consequences

- A user who is removed from an org but still exists keeps their connector auth — it is *their* token.
- Deleting the user account cleanly removes all of their third-party tokens.
- Org-level scoping of which connectors are *usable* is enforced separately through the connector instance, which is org-owned.
