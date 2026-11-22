# Local-only runner: the pinned base digest is chosen by --build-arg BASE_IMAGE.
# No project source or credentials are copied into the image.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install --no-install-recommends -y git nodejs && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65534:65534
WORKDIR /work
