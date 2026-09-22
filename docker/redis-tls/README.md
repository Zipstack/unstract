# Testing against a managed-like Redis locally (UN-4123)

A managed Redis (Memorystore, ElastiCache, Azure Cache) differs from the dev Redis
in exactly two ways our code has to handle: it **requires AUTH** and it **speaks
TLS**. `docker-compose-redis-tls.yaml` runs a Redis that does both, so the TLS path
can be exercised without cloud access or a VPN.

It runs **alongside** the normal `unstract-redis` on port 6380, so nothing switches
until you point services at it — the point of the exercise is to flip between the
two and confirm both work.

Its plaintext listener is disabled (`--port 0`), the same as Azure Cache's default.
A service that fails to pick up the TLS settings therefore *cannot* quietly succeed
over plaintext and hide the bug.

## Start it

```bash
cd docker
./redis-tls/generate-certs.sh
docker compose -f docker-compose-redis-tls.yaml up -d
```

Certificates are self-signed and dev-only. The SAN list covers both names the same
server answers to — `unstract-redis-managed` from inside the network,
`localhost` from a backend on the host — because a certificate valid for only one
fails verification from the other side, which looks like a code bug and is not one.

Confirm it is up, and that plaintext is refused:

```bash
docker exec unstract-redis-managed redis-cli --tls -p 6380 \
  --cacert /certs/ca.crt -a devpassword --no-auth-warning ping   # PONG
docker exec unstract-redis-managed redis-cli -p 6380 \
  -a devpassword --no-auth-warning ping                          # I/O error
```

## Switch the platform onto it

Two values differ by where the process runs: containers reach it as
`unstract-redis-managed:6380`, a backend on the host as `localhost:6380`.

**`backend/.env`** (runs on the host):

```bash
REDIS_URL=rediss://:devpassword@localhost:6380/0?ssl_cert_reqs=required
REDIS_SSL_CA_CERTS=/abs/path/to/unstract/docker/redis-tls/certs/ca.crt
```

**`workers/.env`, `platform-service/.env`** (containers):

```bash
REDIS_URL=rediss://:devpassword@unstract-redis-managed:6380/0?ssl_cert_reqs=required
REDIS_SSL_CA_CERTS=/certs/ca.crt
CACHE_REDIS_URL=rediss://:devpassword@unstract-redis-managed:6380/1?ssl_cert_reqs=required
```

Those containers need the CA mounted. Add to your `docker/compose.override.yaml`:

```yaml
services:
  worker-pg-orchestrator-general:   # repeat for each worker + platform-service
    volumes:
      - ./redis-tls/certs:/certs:ro
```

**`runner/.env`** — one deliberate difference:

```bash
REDIS_URL=rediss://:devpassword@unstract-redis-managed:6380/0
REDIS_SSL_CERT_REQS=none
```

The runner forwards these to each **tool sidecar** it spawns, and sidecars get no
CA mount — the runner builds their environment as an allowlist and mounts only the
shared log dir. `none` keeps the connection encrypted while skipping verification,
which still exercises the forwarding fix and the TLS handshake.

`REDIS_SSL_CERT_REQS` is honoured **alongside** a URL: the setting is resolved
once, with the generic fallback, and applied to `rediss://` URLs that carry no
`ssl_cert_reqs=` of their own. (It did not used to be, which made this recipe
silently fall back to `required` and fail the handshake against the self-signed
dev cert.) Putting it in the URL works too and wins if both are set:
`rediss://:devpassword@unstract-redis-managed:6380/0?ssl_cert_reqs=none`.

Hostname verification follows the same setting — it is forced off when
verification is off, and on otherwise. The dev certificate carries SANs for
`unstract-redis-managed`, `localhost` and `127.0.0.1`, so `required` works from
containers and from the host without further configuration. Against a real
managed endpoint this does not arise: ElastiCache and Azure chain to public CAs, and
for Memorystore you would mount its CA into the sidecar image.

Then restart: `docker compose restart` for the containers, and your usual manual
restart for the backend.

## What to check

1. **An execution completes.** Include a workflow that uses a **container-based
   tool** (classifier or text_extractor) — a Prompt Studio structure tool runs
   in-process in the executor and never spawns a sidecar, so it leaves the whole
   sidecar path untested.
2. **Logs stream in the UI and land in `execution_log`.** That is the Redis-list
   transport end to end, the part with no unit-test coverage.
3. **The keys are in the new server, and the old one is idle:**

   ```bash
   docker exec unstract-redis-managed redis-cli --tls -p 6380 \
     --cacert /certs/ca.crt -a devpassword --no-auth-warning dbsize
   docker exec unstract-redis redis-cli dbsize     # should not be growing
   ```

4. **Nothing fell back to plaintext.** The TLS-only listener makes this
   self-enforcing: a component that missed the settings fails loudly instead.

## Switch back

Remove the `REDIS_URL` / `REDIS_SSL_*` lines, restart, and run the same execution
again. Both modes are supported and both must pass — that is the acceptance bar,
not just "TLS works".

## Against a real managed Redis

Same env, different endpoint. Memorystore is VPC-private, so from a laptop it needs
a tunnel:

```bash
gcloud compute ssh <bastion> -- -L 6380:<memorystore-ip>:6379
REDIS_URL=rediss://:<auth-string>@localhost:6380/0?ssl_cert_reqs=required
```

Drop the `rediss` to `redis` when the instance has TLS disabled — an AUTH string
without in-transit encryption is a supported configuration and worth testing too,
since it is what a VPC-internal deployment may well run.
