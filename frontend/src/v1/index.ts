/*
 * Public entry of the v1 frontend — the only v1 module v0 may import, as
 * `@v1`. Lint rejects any other v0 → v1 import (see src/v1/README.md).
 *
 * Empty until the version switch (UN-4271) mounts v1 through it.
 */
// TEST BRANCH ONLY: the Lane B preview page. Never merged.
export { V1Preview } from "@v1/app/Preview";
