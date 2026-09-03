# ADR-005: Prompt Studio Registry as the publish gate

## Context

Prompt Studio is the authoring surface where prompts are drafted, iterated, and tested. Letting workflow runtime read directly from authoring tables would couple every running execution to in-progress edits, and would let an unsaved draft change the behaviour of a deployed workflow.

## Decision

Prompt Studio publishes a runnable artifact to `PromptStudioRegistry`. The registry is the only surface that runtime consumers may read. Drafts in Prompt Studio are not visible to executors until they are published.

This is the embodiment of P3 (publishing is an explicit gate) for the prompt authoring path.

## Consequences

- Drafts are safe to iterate without affecting running deployments.
- A publish step exists and must succeed before a workflow can use the new prompt configuration.
- Runtime code paths must consult the registry, never the authoring tables directly.
