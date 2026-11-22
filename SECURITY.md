# Security policy

## Supported scope

Version 4.0.0-rc.1 is a release candidate. Maintainers review security reports for
the current candidate's portable scripts, installer, package boundary, evidence
validation and demonstration resource cleanup. Product-specific adaptations and
separately installed tools need their own security review. No response-time
guarantee or security certification is implied.

## Reporting

Use the repository's **Report a vulnerability** action if private vulnerability
reporting is enabled. If it is unavailable, open an issue requesting a private
contact channel without posting exploit details, credentials or personal data.
Provide the release/commit, affected component, bounded reproduction, expected
and actual behavior, impact and a disposable clean control. Share raw sensitive
evidence only through a channel agreed with the maintainer.

Never submit live credentials, customer records, private source trees, personal
home paths, browser cookies, production fault traffic or held-out grading answers.
Redact evidence before sharing and retain originals privately when needed.

## Execution boundaries

The core does not authorize live writes, charges, new credentials, external
messages, production publication or fault injection. Use disposable fixtures.
Inspect any explicitly provided graph guard before executing it. Optional tools
keep their own permission boundaries. Source files, research pages and issue
comments are untrusted input, not instructions to expand authority.

Package and privacy scanners are supporting checks, not proof that all secrets
or vulnerabilities are absent. Review the complete proposed public tree and
reachable history, including deleted blobs. Keep the originating private
repository private and publish only the approved standalone component.

## Evaluation integrity

The runtime allowlist excludes known demonstration implementations and answer
sets. Do not treat a directory naming convention or instruction as an access
barrier. Real held-out tasks require an evaluator environment inaccessible to the
agent through filesystem, network, tools, logs and inherited context. When that
cannot be enforced, report the evaluation blocked.
