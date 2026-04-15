# Documentation Fix Notes

This note summarizes the documentation consistency fixes applied to the repository.

## Scope

- Installation instructions in `README.md` and `README_zh.md`
- Skill documentation for environment setup, code check, dev loop, project creation, and device authorization
- Official documentation links that moved from `tuyaopen.ai` to `tuyaopen.io`

## Fixed Issues

1. Corrected copy and symlink commands so they create parent directories and avoid nesting `skills/skills/...`.
2. Clarified that script-based skills expect a project-local install at `.agents/skills/`.
3. Fixed bundled script paths in skill docs:
   - `.agents/skills/tuyaopen-env-setup/scripts/check_env.sh`
   - `.agents/skills/tuyaopen-code-check/scripts/check_files.sh`
   - `.agents/skills/tuyaopen-dev-loop/scripts/build_run_linux.sh`
4. Fixed `tos.py new project` command examples in `tuyaopen-project-config`.
5. Replaced outdated or broken documentation links with current `tuyaopen.io` links.
6. Updated the repository structure section to include `agent-hardware-debug-helper-tools`.

## Rationale

The original docs mixed multiple install locations with command examples that assumed a fixed repo-local path. They also contained at least one broken documentation URL and several shell commands that would fail as written. These fixes make the documentation internally consistent and executable as-is.
