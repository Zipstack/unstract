/**
 * Test data through the API, removed after the test.
 *
 *   const wf = await seed.create<{ id: string }>("workflow/", {
 *     workflow_name: seed.name("wf"),
 *   });
 *
 * Paths are relative to the org-scoped API root
 * (`/api/v1/unstract/<orgId>/`). Everything created is deleted in reverse
 * order when the test ends, pass or fail. A delete that fails fails the test:
 * the suite shares one org, so leaked rows would leak into other specs.
 */

import { randomUUID } from "node:crypto";
import { test as authTest } from "./auth.ts";
import { BACKEND_URL } from "./env.ts";

export interface CreateOptions<T> {
  /** Field holding the new row's id. Default `id`. */
  idField?: string;
  /** Delete path for the created row. Default `<path>/<id>/`. */
  deletePath?: (created: T) => string;
}

export interface Seed {
  /** `${BACKEND}/api/v1/unstract/<orgId>`, no trailing slash. */
  prefix: string;
  /** A unique, recognisable name for seeded rows: `e2e-v1-<label>-<id>`. */
  name(label: string): string;
  create<T extends object>(
    path: string,
    body: unknown,
    options?: CreateOptions<T>,
  ): Promise<T>;
}

function join(prefix: string, path: string): string {
  return `${prefix}/${path.replace(/^\//, "")}`;
}

export const test = authTest.extend<{ seed: Seed }>({
  seed: async ({ session }, use) => {
    const prefix = `${BACKEND_URL}/api/v1/unstract/${session.orgId}`;
    const cleanups: { url: string; label: string }[] = [];

    await use({
      prefix,
      name: (label) => `e2e-v1-${label}-${randomUUID().slice(0, 8)}`,
      async create<T extends object>(
        path: string,
        body: unknown,
        options: CreateOptions<T> = {},
      ): Promise<T> {
        const url = join(prefix, path);
        const res = await session.api.post(url, {
          data: body,
          headers: await session.csrfHeaders(),
          failOnStatusCode: false,
        });
        if (!res.ok()) {
          throw new Error(
            `seed POST ${url} -> ${res.status()}: ${await res.text()}`,
          );
        }
        const created = (await res.json()) as T;
        const id = (created as Record<string, unknown>)[
          options.idField ?? "id"
        ];
        const deletePath =
          options.deletePath?.(created) ??
          (id === undefined
            ? undefined
            : `${path.replace(/\/$/, "")}/${String(id)}/`);
        if (!deletePath) {
          throw new Error(
            `seed POST ${url} returned no "${options.idField ?? "id"}"; pass idField or deletePath`,
          );
        }
        cleanups.push({ url: join(prefix, deletePath), label: path });
        return created;
      },
    });

    const leaks: string[] = [];
    for (const { url, label } of cleanups.reverse()) {
      const res = await session.api
        .delete(url, {
          headers: await session.csrfHeaders(),
          failOnStatusCode: false,
        })
        .catch((err: Error) => err);
      // 404: the test already deleted it, which is fine.
      if (res instanceof Error) {
        leaks.push(`${label} (${url}): ${res.message}`);
      } else if (!res.ok() && res.status() !== 404) {
        leaks.push(`${label} (${url}): ${res.status()}`);
      }
    }
    if (leaks.length) {
      throw new Error(`seed teardown leaked rows:\n  ${leaks.join("\n  ")}`);
    }
  },
});
