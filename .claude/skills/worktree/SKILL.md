---
name: worktree
description: Creates git worktrees for isolated development. Use when user wants to "create a worktree", "start a new feature branch", "work on a fix in isolation", or needs a parallel development environment.
---

# Git Worktree Management Skill

Create isolated git worktrees for parallel development with automatic config handling.

## Workflow

### Phase 1: Create Worktree

1. **Detect repo info**
   ```bash
   # Get repo name from git remote or directory
   REPO_NAME=$(basename -s .git $(git config --get remote.origin.url) 2>/dev/null || basename $(pwd))
   SOURCE_REPO=$(git rev-parse --show-toplevel)
   ```

2. **Parse user description**
   - Extract work type from description: `fix`, `feat`, or `misc`
   - If user says "fix", "bug", "patch" → type = `fix`
   - If user says "feature", "add", "implement" → type = `feat`
   - Otherwise → type = `misc`
   - Convert remaining description to kebab-case, max 30 chars total for branch name

3. **Generate names**
   - Branch name: `{type}/{kebab-description}`
   - Worktree folder: `{type}-{kebab-description}`
   - Worktree path: `{SOURCE_REPO}/../{REPO_NAME}-worktrees/{worktree-folder}/`

4. **Create worktree**
   ```bash
   git fetch origin main
   WORKTREE_PATH="{source}/../{repo}-worktrees/{folder}"
   mkdir -p "$(dirname "$WORKTREE_PATH")"
   git worktree add -b "{branch}" "$WORKTREE_PATH" origin/main
   ```

5. **Copy config files**

   **If repo is `unstract`:**
   Run the setup script from the source repo:
   ```bash
   "$SOURCE_REPO/scripts/worktree-setup.sh" "$WORKTREE_PATH" "$SOURCE_REPO"
   ```

   **If repo is NOT unstract:**
   Ask user: "Which config files should I copy to the new worktree? (e.g., .env files, config files)"
   Then copy specified files from source to worktree.

6. **Switch to worktree**
   ```bash
   cd "$WORKTREE_PATH"
   ```

7. **Print summary**
   ```
   Worktree created successfully!

   Branch: {branch}
   Path: {worktree_path}

   To switch back to main repo: cd {source_repo}
   To remove worktree later: git worktree remove {worktree_path}
   ```

---

### Phase 2: Build & Run (End of Development)

When user is done with changes and wants to build/run:

1. **Detect changed services** (unstract only)
   ```bash
   git diff --name-only origin/main
   ```

2. **Map directories to services**

   | Changed Directory | Docker Services |
   |-------------------|-----------------|
   | `frontend/` | frontend |
   | `backend/` | backend, worker, worker-logging, worker-file-processing, worker-file-processing-callback |
   | `platform-service/` | platform-service |
   | `prompt-service/` | prompt-service |
   | `runner/` | runner |
   | `workers/` | worker-api-deployment-v2, worker-callback-v2, worker-file-processing-v2, worker-general-v2, worker-notification-v2, worker-log-consumer-v2, worker-scheduler-v2 |
   | `x2text-service/` | x2text-service |
   | `unstract/` | backend, platform-service, prompt-service |
   | `docker/dockerfiles/*.Dockerfile` | Service matching dockerfile name |

3. **Offer to build changed services**
   ```bash
   cd docker
   VERSION=test docker compose -f docker-compose.yaml -f compose.override.yaml build {services}
   ```

4. **Offer to run services**

   With workers-v2 profile:
   ```bash
   VERSION=test docker compose -f docker-compose.yaml -f compose.override.yaml --profile workers-v2 watch
   ```

   Without workers-v2 (v1 workers):
   ```bash
   VERSION=test docker compose -f docker-compose.yaml -f compose.override.yaml watch
   ```

---

## Examples

**User:** "create a worktree for fixing the login bug"
- Type: `fix`
- Branch: `fix/login-bug`
- Folder: `fix-login-bug`

**User:** "worktree for adding user notifications"
- Type: `feat`
- Branch: `feat/user-notifications`
- Folder: `feat-user-notifications`

**User:** "new worktree for refactoring"
- Type: `misc`
- Branch: `misc/refactoring`
- Folder: `misc-refactoring`

---

## Useful Commands Reference

**List worktrees:**
```bash
git worktree list
```

**Remove worktree:**
```bash
git worktree remove {path}
```

**Prune stale worktrees:**
```bash
git worktree prune
```
