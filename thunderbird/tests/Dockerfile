# SPDX-License-Identifier: LGPL-2.1-or-later
# Standalone dependency proof: no Evolution, Camel, EDS or libical development files.
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS build
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build pkgconf libglib2.0-dev libsoup-3.0-dev \
    libxml2-dev libjson-glib-dev python3 openssl nodejs ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 1000 developer && useradd --uid 1000 --gid 1000 --no-create-home developer
WORKDIR /src
USER 1000:1000

FROM build AS runtime
USER root
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    thunderbird xvfb xauth && rm -rf /var/lib/apt/lists/*
USER 1000:1000
