# Container Runtime Support (Docker & Podman)

The Unstract docker-compose configuration supports both **Docker** (default) and **Podman**.

## Socket Detection

The configuration defaults to Docker and supports Podman via environment variable:
- **Docker**: Default (`/var/run/docker.sock`) - no configuration needed
- **Podman**: Set `DOCKER_SOCKET=${XDG_RUNTIME_DIR}/podman/podman.sock`

## Using Docker

Docker works out of the box with no additional configuration:

```bash
VERSION=main docker-compose -f docker-compose.yaml up -d
```

The Docker socket at `/var/run/docker.sock` is used automatically.

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

Set the `DOCKER_SOCKET` environment variable to point to Podman socket, then run podman-compose:

```bash
export DOCKER_SOCKET=${XDG_RUNTIME_DIR}/podman/podman.sock
VERSION=main podman-compose -f docker-compose.yaml up -d
```

**Note**: The `DOCKER_SOCKET` environment variable must be set to use Podman instead of the default Docker socket.

## Custom Socket Path

If you need to specify a custom socket path, set the `DOCKER_SOCKET` environment variable:

```bash
# Example: Custom Docker socket location
export DOCKER_SOCKET=/custom/path/docker.sock
VERSION=main docker-compose -f docker-compose.yaml up -d

# Example: Alternative Podman socket location
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

The configuration uses this simple priority:

1. `$DOCKER_SOCKET` - if explicitly set (use this for Podman or custom paths)
2. `/var/run/docker.sock` - default (Docker standard socket)

**Docker**: No configuration needed - uses default socket
**Podman**: Set `export DOCKER_SOCKET=${XDG_RUNTIME_DIR}/podman/podman.sock`

## Technical Details

The docker-compose files use this volume mount configuration:

```yaml
volumes:
  - ${DOCKER_SOCKET:-/var/run/docker.sock}:/var/run/docker.sock
```

This means:
- If `DOCKER_SOCKET` is set → use that path (for Podman or custom Docker socket)
- Else → use `/var/run/docker.sock` (Docker default)

**For Podman users:**
```bash
export DOCKER_SOCKET=${XDG_RUNTIME_DIR}/podman/podman.sock
```

This overrides the default Docker socket with the Podman socket path.
