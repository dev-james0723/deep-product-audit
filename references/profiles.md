# Profiles

Use one core and evidence format. Do not maintain competing copies with different completion rules.

| Profile | Work | Evidence |
| --- | --- | --- |
| coordinator | Scope, independent lanes, duplicates, gaps | Coverage matrix, prioritized findings, next owners |
| designer | Hierarchy, clarity, consistency, accessibility, motion, responsiveness | Annotated observations, user impact, separate suggestions |
| qa | Journeys, edge cases, recovery, browsers, viewports | Steps, expected/actual results, runtime evidence |
| engineer | Source/data boundaries, authorized repair | Hypothesis, confirming experiment, focused regression |
| security | Authorized role/tenant boundaries, input/session behavior | Demonstrated access results; no pass from visibility |
| verifier | Independently reproduce or refute material candidates and fixes | Raw evidence review, alternative explanations, confirmed/rejected/needs-validation |
| release | Build/source/deployment reconciliation, critical paths | Exact environment/artifact, observed outcome |

## Standard

Discover scope/tools, perform relevant real checks, record evidence, and report honest gaps. A designer or QA task may use its role lane. Standard mode retains the same truth and authority requirements.

## Advanced: source-aware engineering

Use advanced when the task includes source review and authorized repair. Perform relevant lanes, inspect source/tests, validate integration boundaries, create focused regressions, and verify authorized repairs. Read advanced.md. Prefer native subagents unless the user selected another orchestrator. Parallelize independent read-only work or isolated owned edits; retain one coordinator and coordinate writers per shared resource/session. Independent devices/sessions need not wait behind an unrelated GUI writer.

Advanced is a workflow profile, not a model change or permission upgrade. Preserve selected models and native safety settings. Do not install hooks or enable paid routes merely to activate a skill.

## Optional agent-host assignment

1. Discover the real roster and skill catalog through documented API/UI.
2. Match observed responsibilities to profiles, not guessed names.
3. Preserve existing skills/settings; add this skill and its profile.
4. Use supported skill/instruction fields. Do not invent config files the host ignores.
5. Verify catalog content and agent associations with a fresh read. If a provider does not load native skills, verify actual host prompt assembly or supported delivery.
6. Separate saved assignment, provider discovery, successful invocation, and end-to-end audit. Running conversations may load changes on a subsequent normal turn/session.

Do not send tasks to agents merely to prove assignment. Use a harmless approved fixture or supported diagnostic and identify invocations not yet tested.
