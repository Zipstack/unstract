# Generate uv.lock file

Helps generate uv's lockfiles by running `uv sync` on all necessary packages and services.

It also detects **transitive dependency changes** — if a local path dependency's `pyproject.toml` changed (e.g. `unstract/sdk1`), all services that depend on it (e.g. `backend`, `prompt-service`) will have their lockfiles regenerated too.

- project root
- `backend`
- `prompt-service`
- `runner`
- `unstract/core`
- `unstract/flags`
- `platform-service`
- `x2text-service`
- `unstract/connectors`
- `unstract/tool-sandbox`

Can be run without any arguments to check for lockfile generation on all necessary packages and services
```shell
./uv-lock.sh
```

Accepts a list of directories to generate for as command line arguments
```shell
./uv-lock.sh backend prompt-service
```
