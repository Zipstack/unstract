/*
 * Public entry of the v1 frontend — the only v1 module v0 may import, as
 * `@v1`. Lint rejects any other v0 → v1 import (see src/v1/README.md).
 *
 * Keep this light: v0 loads it eagerly, so it holds the version switch and
 * the registry, and the v1 tree itself loads only when a v1 page renders.
 */

export {
  resolveUrl,
  setOldVersion,
  v1DevRoutesEnabled,
} from "@v1/app/api";
export type {
  Distribution,
  PageKey,
  RegistryEntry,
} from "@v1/app/registry/types";
export { VersionSwitch, type VersionSwitchProps } from "@v1/app/VersionSwitch";
