# Advanced engineering workflow

## Baseline and parallel lanes

Read current instructions, revision, dirty state, relevant source/test scripts, services, and task ownership. Respect leases and use isolated worktrees where needed. Reuse dependencies and existing/owned servers; avoid duplicate heavyweight suites.

Split independent discovery/UX, behavior/access, and source/integration work only when useful. Share compact scope and evidence contracts. Isolate test data/browser sessions. Consolidate by failing journey, expected behavior, and affected boundary.

## Source to runtime

Follow important control handlers, service/API calls, persistence, reload, errors, and permissions. Look for mock data, feature flags, placeholder callbacks, disconnected settings, and optimistic UI hiding failures. Reproduce candidates or clearly mark them source-only risks.

Use authoritative artifact/version/deployment records to establish release identity. Missing identity stays unknown; do not mutate production to manufacture a marker.

## Playwright

Use the installed project version/config. Prefer accessible locators and web-first assertions; wait for actual state instead of fixed sleeps. Preserve original failures. Capture targeted traces and retain runner results because context tracing does not itself include assertions.

Optional official definitions support playwright init-agents --loop=claude and --loop=codex in current versions. Verify installed help before use; inspect and preserve existing definitions. Generated agents remain within the project's existing coordination and permission model.

## Root cause

1. Reproduce stable input and expected result.
2. Inspect the boundary where behavior first diverges; compare working paths.
3. State one disprovable hypothesis; instrument minimally without private data.
4. Run the experiment; retain uncertainty until the cause is supported.
5. Apply a focused repair if authorized; preserve unrelated work.
6. Rerun the original failure and necessary nearby regression.

Do not weaken assertions, skip failing flows, or repeat unchanged failures. Avoid resets, restarts, cache deletions, and dependency changes without a specific causal reason.

## Delivery

Follow existing task/repository authorization for commit, merge, deployment, and rollback. Finish authorized release checks and verify runtime behavior. Otherwise report the precise local/branch/staging state.

For every completion claim identify requirement, build, environment, observed outcome, and remaining uncertainty.
