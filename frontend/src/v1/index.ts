/*
 * The v1 public entry: the one module v0 may import (the version switch
 * mounts v1 through it). Everything else under src/v1/ is private to v1;
 * scripts/v1-boundary.mjs fails lint on any other v0 -> v1 import.
 */
export const V1_PUBLIC_ENTRY = "v1";
