# Offline-capable local CI — optional contributor tooling

Use this when hosted CI is unavailable, billing-locked or unwanted. It runs the **unchanged** project test suite and bounded disposable integration checks. It does not require GitHub Actions, Cloud services, a paid account, Codex, or a deployed product. The core skill does not preload any local-CI configuration.

## Safety and boundaries

- Native Python runs with a disposable `HOME` and a small environment allowlist; **never** supply personal API tokens or sensitive credentials as test fixtures.
- Linux uses an **already running**, explicitly selected Docker context. It has no network, no writable source mount, and limits CPU (2), memory (1.5 GiB), processes (128) and writable temporary storage (512 MiB). It creates no persistent container and cannot modify other running containers.
- Images must be built by the operator; the test runner refuses missing images and never implicitly pulls a new image. Base image digests below were verified during the 2026-11-21 QA run; verify the image source and subsequent package updates before rebuilding.
- Keep receipts **outside** the repo. They may contain temporary paths, and logs must be inspected before being shared publicly. Each result stores exit code, count, skips and SHA-256 of stdout/stderr.
- The matrix fails if any expected receipt is missing, dirty, from another commit or has modified logs. A passing Linux VM/container is **not a native Windows test**. Release approval and deployment are never automatic.

## Build two local Linux ARM64 images (one-time)

This only works where Docker Engine is already running. Replace `YOUR_CONTEXT` with an **explicit, trusted** context. The image build may access Debian package repositories to install `git` and `nodejs`; the **test run is offline**. Do not build or run these images in another team's busy container profile without coordinating resources.

```sh
docker --context YOUR_CONTEXT pull --platform linux/arm64 \
  python:3.10.16-slim-bookworm@sha256:f9fd9a142c9e3bc54d906053b756eb7e7e386ee1cf784d82c251cf640c502512
docker --context YOUR_CONTEXT pull --platform linux/arm64 \
  python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0

docker --context YOUR_CONTEXT build --pull=false --platform linux/arm64 \
  -f tools/localci/Dockerfile \
  --build-arg BASE_IMAGE=python:3.10.16-slim-bookworm@sha256:f9fd9a142c9e3bc54d906053b756eb7e7e386ee1cf784d82c251cf640c502512 \
  -t deep-product-audit-localci:py310-20261121 .
docker --context YOUR_CONTEXT build --pull=false --platform linux/arm64 \
  -f tools/localci/Dockerfile \
  --build-arg BASE_IMAGE=python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0 \
  -t deep-product-audit-localci:py312-20261121 .
```

## Run per lane from a **clean, committed checkout**

```sh
python3 -B tools/local_ci.py --runner native --python /absolute/path/to/python3.12 \
  --min-tests 246 --out ../ci-results/macos-python312

python3 -B tools/local_ci.py --runner linux-docker \
  --docker-context YOUR_CONTEXT --image deep-product-audit-localci:py310-20261121 \
  --min-tests 246 --out ../ci-results/linux-python310
```

Repeat with each interpreter/image in [`matrix.json`](matrix.json). Do not run multiple writers against the same source and report path. A first attempt with dirty/uncommitted files may execute tests but **will not pass matrix acceptance**.

## Verify the whole local matrix

```sh
python3 -B tools/localci/aggregate.py --runs ../ci-results \
  --expected-runtime-sha256 \
  9fd64f683c671cd3845fbd6f0b42dd8af631e91b09d2e941c72f62b0a7189763 \
  --out ../ci-summary.json
```

The default matrix expects four macOS Python lanes (3.10, 3.11, 3.12, 3.15) and two Linux ARM64 lanes (3.10, 3.12). Adapt it to your own machine if some lanes are genuinely unsupported, but **record those explicitly as not tested**, do not silently remove them while claiming equivalent coverage. For another product version, update the required test count and runtime archive digest only after independently verifying the expected values. Logs are not uploaded automatically.

## Cleanup

The Docker test containers self-remove (`--rm`); temporary native test homes are deleted after a lane. Images are retained for reproducibility. If you no longer need these *exact project-owned* images, run explicit `docker --context YOUR_CONTEXT image rm ...` commands for their tags only, never a global `system prune`. Preserve receipts and the reviewed Git commit while release acceptance is pending.

**Blocked:** A Windows-native runner was not available in the recorded environment. Hosted GitHub Actions returned an account billing lock before job startup; local Linux containers do not solve this limitation. Keep Windows as `not_tested` until a native Windows environment executes a fresh, independently reviewed lane.
