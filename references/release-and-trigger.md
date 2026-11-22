> Trigger-label scoring is an optional maintainer activity in the full source checkout. Trigger labels and evaluator-only demonstrations are excluded from the runtime install.

# Release observation, product profiles and trigger accuracy

## Post-release evidence

First verify approved source revision -> artifact digest -> observed deployed revision -> running target identity and deploy timestamp. Freeze scope and monitoring objectives before testing. Record two or more separate independent observation windows: request counts/error counts, p95, dropped iterations, actual synthetic journey outcomes, independent backend health and rollback drill evidence. Keep redacted local artifacts in one private bundle.

Use real, project-specific thresholds. Example shape:

    {
      "schema_version":1,
      "identity":{"source_revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "deployed_source_revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "observed_source_revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "artifact_sha256":"<actual-64-hex-digest>", "environment":"staging", "evidence":[{"path":"identity.json","sha256":"<actual-64-hex-digest>"}]},
      "thresholds":{"max_error_ratio":0.01,"max_p95_ms":500,"max_dropped_iterations":0,"min_requests_per_window":50},
      "probes":[{"id":"journey-1","status":"passed","evidence":[{"path":"journey-1.json","sha256":"<actual-64-hex-digest>"}]}],
      "windows":[{"id":"w1","start_at":"2026-11-21T18:00:00-05:00","end_at":"2026-11-21T18:05:00-05:00","observed_source_revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","requests":100,"errors":0,"p95_ms":120,"dropped_iterations":0,"evidence":[{"path":"w1.json","sha256":"<actual-64-hex-digest>"}]},
                 {"id":"w2","start_at":"2026-11-21T18:05:00-05:00","end_at":"2026-11-21T18:10:00-05:00","observed_source_revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","requests":100,"errors":0,"p95_ms":130,"dropped_iterations":0,"evidence":[{"path":"w2.json","sha256":"<actual-64-hex-digest>"}]}],
      "rollback":{"verified":true,"run_id":"real-rehearsal-run-id","status":"passed","evidence":[{"path":"rollback.json","sha256":"<actual-64-hex-digest>"}]}
    }

Run:

    python3 <skill>/scripts/release_observer.py <contract.json> --out <new-report.json>

Requires real revision, artifact/evidence digests, separate non-overlapping post-deployment time ranges, distinct phase evidence, and matching stage-specific JSON receipts (`release_identity`, `synthetic_journey`, `telemetry_window`, `rollback_rehearsal`); above text is illustrative and not executable as-is. An observation gate marked eligible is merely a verified *record format*; an independent witness still has to inspect actual logs, deployed identity, thresholds and rollback drill. The helper never hits the network, deploys, exercises a failover, or approves production.

## Product profiles

assets/product-profiles.json contains optional risk suggestions for multi-tenant web services, native editors, device-control tools and integration services. Verify these journeys truly exist in current repo. Do not treat a proposed invariant or role as a performed test, or infer an unverified feature is shipped.

## Skill trigger performance

assets/trigger-cases.json has 10 positive and 10 negative prompts. Collect actual agent skill-loading logs into a schema_version 1 file with observations [{case_id,triggered,run_id,agent_session}], then score:

    python3 <skill>/scripts/evaluate_triggers.py --manifest <skill>/assets/trigger-cases.json --observations <actual-observations.json> --out <new-score.json>

The scorer cannot authenticate host receipts and does not invoke the agent itself. Incomplete observations remain unmeasured, never a true negative. Test conflicts with other testing/design skills, ensure one product-audit coordinator, and do not create multiple GUI writers for a single session. Do not automatically load this skill for essays, general explanations, social writing or pure image requests.
