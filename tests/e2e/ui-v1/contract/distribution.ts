/**
 * The distribution this run checks, from UNSTRACT_DISTRIBUTION. It must match
 * the image's VITE_DISTRIBUTION, which decides the pages it renders; nothing
 * can check that from here. Read like the app's parseDistribution: unset or
 * empty means oss.
 */

import {
  DISTRIBUTIONS,
  type Distribution,
} from "../../../../frontend/src/v1/app/registry/types.ts";

export function currentDistribution(): Distribution {
  const raw = process.env.UNSTRACT_DISTRIBUTION?.trim().toLowerCase() || "oss";
  const distribution = DISTRIBUTIONS.find((d) => d === raw);
  if (!distribution) {
    throw new Error(
      `UNSTRACT_DISTRIBUTION=${raw} is not one of ${DISTRIBUTIONS.join(", ")}`,
    );
  }
  return distribution;
}
