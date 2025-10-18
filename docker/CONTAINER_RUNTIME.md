# Container Runtime Support (Docker & Podman)

The Unstract docker-compose configuration supports both **Docker** and **Podman** automatically.

## Automatic Detection

By default, the configuration will automatically detect and use the appropriate socket:
- **Podman rootless**: `/run/user/$UID/podman/podman.sock`
- **Docker**: `/var/run/docker.sock`

## Using Docker

Just run docker-compose commands normally:

```bash
VERSION=main docker-compose -f docker-compose.yaml up -d
```

No environment variables needed - Docker socket at `/var/run/docker.sock` will be used automatically.

## Using Podman

### Prerequisites

1. **Enable Podman socket** (required for Traefik to discover containers):
   ```bash
   systemctl --user enable podman.socket
   systemctl --user start podman.socket
   ```

2. **Verify socket is running**:
   ```bash
   systemctl --user status podman.socket
   # Should show: active (listening)
   ```

### Run with Podman

```bash
VERSION=main podman-compose -f docker-compose.yaml up -d
```

The Podman socket will be automatically detected via `$XDG_RUNTIME_DIR/podman/podman.sock`.

## Manual Override

If you need to specify a custom socket path, set the `DOCKER_SOCKET` environment variable:

```bash
# Example: Custom Docker socket location
export DOCKER_SOCKET=/custom/path/docker.sock
VERSION=main docker-compose -f docker-compose.yaml up -d

# Example: Custom Podman socket location
export DOCKER_SOCKET=/run/user/$(id -u)/podman/podman.sock
VERSION=main podman-compose -f docker-compose.yaml up -d
```

## Troubleshooting

### Traefik shows "Cannot connect to Docker daemon"

**For Podman users**:
1. Check if Podman socket is running:
   ```bash
   systemctl --user status podman.socket
   ```

2. If inactive, start it:
   ```bash
   systemctl --user start podman.socket
   ```

3. Verify socket file exists:
   ```bash
   ls -la $XDG_RUNTIME_DIR/podman/podman.sock
   # Should show: srw-rw---- (socket file, not directory)
   ```

4. If it's a directory (wrong), remove and restart:
   ```bash
   rmdir $XDG_RUNTIME_DIR/podman/podman.sock
   systemctl --user restart podman.socket
   ```

**For Docker users**:
1. Check if Docker daemon is running:
   ```bash
   systemctl status docker
   ```

2. Verify socket permissions:
   ```bash
   ls -la /var/run/docker.sock
   ```

### Port 8081 not accessible

This is the Traefik HTTP port for Podman rootless compatibility.

1. Check if Traefik container is running:
   ```bash
   podman ps | grep unstract-proxy
   # or
   docker ps | grep unstract-proxy
   ```

2. Check Traefik logs:
   ```bash
   podman logs unstract-proxy
   # or
   docker logs unstract-proxy
   ```

## Socket Path Priority

The configuration uses this priority order:

1. `$DOCKER_SOCKET` - if explicitly set
2. `$XDG_RUNTIME_DIR/podman/podman.sock` - for Podman rootless
3. `/run/user/1000/podman/podman.sock` - fallback for Podman
4. Falls back to default compose behavior (typically `/var/run/docker.sock`)

## Technical Details

The docker-compose files use this volume mount configuration:

```yaml
volumes:
  - ${DOCKER_SOCKET:-${XDG_RUNTIME_DIR:-/run/user/1000}/podman/podman.sock}:/var/run/docker.sock
```

This means:
- If `DOCKER_SOCKET` is set → use that
- Else if `XDG_RUNTIME_DIR` is set → use `$XDG_RUNTIME_DIR/podman/podman.sock`
- Else → use `/run/user/1000/podman/podman.sock`

For Docker, you can set:
```bash
export DOCKER_SOCKET=/var/run/docker.sock
```

But it's usually not necessary since Docker Compose will use `/var/run/docker.sock` by default when the variable is unset.
