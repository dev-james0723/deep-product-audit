# Native, data and distributed product invariants

Select applicable scenarios after inspecting the actual product and requirements. The examples below are proposed coverage, not assertions that any particular product contain these defects. Keep approved fixtures and exact platform/build evidence.

## Target and observation

Use native/mobile target kinds for app identifiers or concrete app locations, API for service roots, and CLI for an executable identity. Initializing a ledger never launches the target. On Mac/iOS, follow current host signing, consent and permission rules; preserve stable identity. A test binary must not reuse the real application's sensitive stores. Never reset TCC/Keychain or interrupt another agent's live app to establish a baseline.

For Swift apps, reuse the project tests: Swift Testing for suitable logic, XCTest/XCUIAutomation for supported UI paths, Instruments and supported sanitizers for specific memory/concurrency/hang questions. Sanitizer overhead changes performance: collect a separate normal-build baseline. Record hardware/OS, display arrangement, locale/timezone, input method, permission state and relevant resource budgets.

## Native failure matrix

| Boundary | Cases | Observation |
| --- | --- | --- |
| Lifecycle | Launch, close, reopen, sleep/wake, background/foreground | Durable state and known pending-operation outcome |
| Multiple surfaces | Multiple windows/displays, independent sessions, competing resources | Correct target and scoped coordination; no cross-window action |
| Permissions | Existing consent, denied/revoked required permission | Honest recoverable state; no repeated consent caused by identity churn |
| Files | Unicode/long paths, unavailable source, disk full, external volume removal | Actual bytes/format, durable result, temporary-file cleanup and recoverability |
| Clipboard/share | Copy, repeated copy, ownership changes, supported export routes | Correct content in the intended surface; no unintended external sends |
| Cancellation | Cancel before/during/after commit and late callbacks | Consistent final state, no late overwrite or unexplained side effect |
| Resource growth | Repeated capture/export, long sessions, background queues | Time-series memory/descriptors/temp files and bounded recovery |
| Accessibility | Keyboard, focus, VoiceOver, zoom/text sizes, reduced motion | Real interaction evidence on the target platform |

## Identity and data boundaries

Use at least two independent ordinary identities plus relevant privileged/anonymous cases when testing peer/tenant isolation. Give each identity owned fixtures and verify the real auth context. Exercise direct API, database/RLS, storage objects, exports, signed links, realtime subscriptions and browser/native caches where present; server checks do not erase already-cached private data after sign-out/account switch.

For Supabase/Postgres, reuse pgTAP/project migrations and role/JWT-aware fixtures. Test SELECT/INSERT/UPDATE/DELETE and returned/affected rows, not only a successful HTTP status or absence of a UI control. Test session expiry/revocation, privilege changes and object ownership transitions. Schema fuzzing can help discover boundary inputs but must not replace the explicit access matrix.

Concurrency invariants should specify the permitted final state: unique business operation, capacity never exceeded, no lost updates, monotonic version, idempotent event application, atomic balance change or explicit conflict. Start competitors with a barrier rather than guessed sleeps, observe durable state independently, and retain transaction/operation IDs. Repeat only to characterize a demonstrated race, keeping every failed attempt.

Time-sensitive business logic needs a controlled clock: timezone/DST transitions, date-only values, boundary instants, expiry and queue delay. Compare business rules to stored UTC/local representations; do not invent the intended policy.

## Product archetypes

| Archetype | Candidate invariants to verify against actual requirements |
| --- | --- |
| Device/session control | Correct device and session; ambiguous delivery reconciled before replay; durable operation identity and cancellation |
| Multi-tenant service | Role and tenant isolation across APIs, exports, storage and realtime; capacity races and durable drafts |
| Native media editor | Import, preview, edit and decodable export; optional network/media modules cannot block basic editing; disk/permission recovery |
| Provider integration | Distinguish auth/quota/network errors; preserve stream/tool state; avoid repeating a committed side effect |

These are scope hypotheses, not product facts or completed tests.

## Primary guidance

- https://developer.apple.com/documentation/technologyoverviews/testing-and-performance
- https://supabase.com/docs/guides/database/postgres/testing-row-level-security
- https://fast-check.dev/docs/advanced/model-based-testing/
- https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
