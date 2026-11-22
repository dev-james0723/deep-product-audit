# Research-derived boundary checks

These checks apply to conventional and AI-assisted software. They test observed
behavior, not the origin of the source code. The accompanying public
`behavior_lab.py` contains known-answer teaching fixtures. Its success proves
only that its unchanged checks distinguish those fixtures. It is not a hidden
benchmark, agent trial, product certification, or comparative detection claim.

## Check catalog

| Check | Failure and affected workflow | Reproduction in an authorized disposable environment | Independent oracle | Negative control and false-positive guard |
| --- | --- | --- | --- | --- |
| Partial batch success | A batch endpoint or tool returns HTTP 200 and a success summary after one child operation failed; a user believes every edit was saved. | Freeze two owned records, make one non-writable through its normal lock rule, submit one batch, then inspect every item and final aggregate. Repeat with a missing item and a permission-denied item. | Query committed rows independently of the response. Match requested IDs, per-item outcomes, aggregate result, and counts. Any partial outcome must remain visible and must not be reported as complete. | An entirely writable batch succeeds. A documented partial-success response with accurate individual errors is correct behavior; HTTP 200 alone is neither a pass nor a defect. |
| Fail-closed privacy parsing | A boolean or enum encoding mismatch silently selects a public channel or weaker authorization path. | With separate authorized and unauthorized identities, send each documented encoding, casing, absent value, invalid value, duplicate key, and explicit public value. Attempt the direct API path as well as the UI. | Server-side authorization decision and independent subscription/delivery records; unauthorized identities must receive no private event or record. Malformed security modes must be rejected or remain restrictive. | Authorized private access succeeds and an intentionally public route stays public. Adopt the product's documented encoding contract; rejecting undocumented casing is not itself a bug. The lab accepts case-insensitive true/false by explicit fixture contract. |
| Atomic concurrent persistence | Two settings writers share the destination file; interleaving truncates data, leaves stale trailing bytes, or loses a valid snapshot. | Use two owned writers and deterministic barriers around open/write/replace. Include different payload lengths, a concurrent reader, restart, and a failed write. For read-modify-write semantics, separately test lost updates and the stated conflict rule. | Decode bytes from a fresh file handle and compare against the allowed complete snapshots. Verify no mixed/partial JSON, unrelated-field loss, leaked temporary files, or false saved state. | A single writer succeeds. For whole-snapshot replacement, a documented last-writer-wins policy is valid. Atomic replacement alone does not solve lost updates or establish crash durability on every filesystem. |
| Truncated stream completion | A stream emits a partial answer and closes early, yet the UI or agent records success or runs the next side effect. | Use an owned loopback transport to cut the stream before its terminal marker and, separately, mid-frame. Test server error, cancel, retry, reconnect and complete transport with a missing application terminal marker. | Raw framing/bytes and the protocol's terminal/error/cancel events, plus persisted operation state. A partial answer may be displayed but must remain explicitly incomplete; reconcile any ambiguous side effects before retrying. | A complete stream reaches its terminal success state. Some protocols permit EOF as completion; use their explicit contract rather than assuming every stream needs a sentinel. The lab's NDJSON contract explicitly requires its final done event. |
| Required CI scope | A green aggregate or zero reported failures conceals skipped, missing, stale, or cancelled required jobs. | Freeze required job IDs, source revision, platform matrix and expected assertions before the run. Supply a skipped or missing required job while retaining a green aggregate; compare the result with a fully executed run. | Exact workflow/job records and artifacts at the required commit, with a denominator covering every required combination. Skipped, blocked, unknown and untested states cannot become passed. | Explicitly optional jobs may be skipped with the preserved rationale. A changed required denominator needs independent review. The lab checks supplied records offline and does not execute a real CI system. |

## Use the demonstration

Run from the full source checkout root. These known fixtures are excluded from
the minimal runtime installation:

```sh
python scripts/behavior_lab.py --out ../result.json
python tools/run_tests.py test_behavior_lab.py
```

The lab starts only owned `127.0.0.1` HTTP servers on assigned ephemeral ports,
uses fresh SQLite databases and temporary directories, and cleans up its own
threads and files. It does not accept a remote target. The output path must not
already exist. A failed environment prerequisite produces `blocked`, not a
seeded-bug reproduction. Nonzero exit means the demonstration was not validated.

The result includes five known bugs, five clean controls, both implementation
modes, the exact observed data, observation digests, runtime/version metadata,
and a SHA-256 over the shared checks, fixture inputs, and expected outcomes before
and after both runs. Ten checks execute per mode. The same assertions remain
unchanged; every clean control must pass in both modes.

The atomic-write fixture uses two coordinated writers, not sleep timing. The
buggy writer keeps an already-truncated handle open while a second writer writes
a longer valid document. The first writer then writes a shorter document,
leaving an invalid tail. The corrected writer publishes its own completed
temporary file with `os.replace`. This models one concrete file-write race;
it does not claim to cover all persistence failures.

## Applying checks to a real audit

Before adapting a fixture, state the actual requirement, identities, environment,
operation budget, cleanup, and independent oracle. Capture the failed runtime
behavior before editing. Reuse the same assertions on the repaired revision.
Keep evidence of both outcomes and have a separate reviewer inspect the actual
records and source. A screenshot or success toast does not replace durable state.

Mark unsupported journeys `blocked` or `not_tested`. Run browser, accessibility,
mobile, payment-provider and deployment checks separately when those capabilities
exist. Never label this local demonstration proof of those integrations.
