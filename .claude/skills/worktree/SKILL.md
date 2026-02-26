---
name: worktree
description: Creates git worktrees for isolated development. Use when user wants to "create a worktree", "start a new feature branch", "work on a fix in isolation", or needs a parallel development environment.
---

# Git Worktree Skill

Create isolated worktrees for parallel development. Ends by providing commands to continue in the new worktree.

## Workflow

1. **Detect repo info**
   ```bash
   REPO_NAME=$(basename -s .git $(git config --get remote.origin.url) 2>/dev/null || basename $(pwd))
   SOURCE_REPO=$(git rev-parse --show-toplevel)
   ```

2. **Parse user description**
   - Type: `fix` (bug, patch, fix) | `feat` (feature, add, implement) | `misc` (default)
   - Branch: `{type}/{kebab-description}` (max 30 chars)
   - Folder: `{type}-{kebab-description}`
   - Path: `{SOURCE_REPO}/../{REPO_NAME}-worktrees/{folder}/`
   - Version: `{kebab-description}` (for docker image tag)

3. **Create worktree**
   ```bash
   git fetch origin main
   mkdir -p "$(dirname "$WORKTREE_PATH")"
   git worktree add -b "{branch}" "$WORKTREE_PATH" origin/main
   ```

4. **Copy config files**
   - **unstract repo:** Run `"$SOURCE_REPO/.claude/skills/worktree/worktree-setup.sh" "$WORKTREE_PATH" "$SOURCE_REPO"`
   - **Other repos:** Ask user which config files to copy, then copy them

5. **Detect services from request** (unstract only)

   Match keywords in user's request to services:

   | Keywords                       | Services                   |
   | ------------------------------ | -------------------------- |
   | frontend, UI, react, component | frontend                   |
   | backend, API, django           | backend                    |
   | platform, adapter, LLM         | platform-service           |
   | prompt, studio                 | prompt-service             |
   | worker, celery, task           | backend (includes workers) |
   | x2text, extraction             | x2text-service             |

   Default if unclear: `backend frontend`

6. **Print summary with commands**

   ```text
   Worktree created!

   Branch: {branch}
   Path: {worktree_path}

   ─────────────────────────────────────────────────────────
   Continue in new worktree and paste your prompt:

   cd {worktree_path} && claude

   {user_request_slightly_made_better_for_new_agent_to_understand}
   ─────────────────────────────────────────────────────────
   Build & run services:

   cd {worktree_path}/docker && \
   VERSION={version} docker compose -f docker-compose.yaml -f compose.override.yaml build {services} && \
   VERSION={version} docker compose -f docker-compose.yaml -f compose.override.yaml watch {services}
   ─────────────────────────────────────────────────────────

   Cleanup later: git worktree remove {worktree_path}
   ```

   IMPORTANT: Escape any quotes in `{user_request}` for shell safety.

## Examples

**User:** "worktree for fixing login validation in frontend"
- Branch: `fix/login-validation`
- Version: `login-validation`
- Services: `frontend`

**User:** "create worktree to add workflow export API"
- Branch: `feat/workflow-export-api`
- Version: `workflow-export-api`
- Services: `backend`

## Reference

```bash
git worktree list          # List worktrees
git worktree remove {path} # Remove worktree
git worktree prune         # Prune stale entries
```
