FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55 AS toolchain

ENV DEBIAN_FRONTEND=noninteractive

ARG UBUNTU_SNAPSHOT=20261014T000000Z
ARG CA_CERTIFICATES=20260601~24.04.1
ARG PPA_POOL=https://ppa.launchpadcontent.net/dciabrin/ngdevkit/ubuntu/pool/main/n
ARG NGDEVKIT_TOOLCHAIN=ngdevkit-toolchain/ngdevkit-toolchain_0.1%2b202606181616-15%7eubuntu24.04.1_amd64.deb
ARG NGDEVKIT=ngdevkit/ngdevkit_0.5%2b202607191609-17%7eubuntu24.04.1_amd64.deb
ARG NGDEVKIT_GNGEO=ngdevkit-gngeo/ngdevkit-gngeo_0.8.1%2b202607271849-11%7eubuntu24.04.1_amd64.deb

RUN apt-get update \
 && apt-get install -y --no-install-recommends "ca-certificates=${CA_CERTIFICATES}" \
 && apt-get update --snapshot "${UBUNTU_SNAPSHOT}" \
 && apt-get install -y --no-install-recommends --snapshot "${UBUNTU_SNAPSHOT}" \
      binutils \
      cppcheck \
      curl \
      make \
      pkg-config \
      python3 \
      rsync \
      zip \
 && rm -rf /var/lib/apt/lists/*

COPY toolchain/ngdevkit.sha256 /tmp/ngdevkit/ngdevkit.sha256

RUN cd /tmp/ngdevkit \
 && curl -fsSL -o ngdevkit-toolchain.deb "${PPA_POOL}/${NGDEVKIT_TOOLCHAIN}" \
 && curl -fsSL -o ngdevkit.deb "${PPA_POOL}/${NGDEVKIT}" \
 && curl -fsSL -o ngdevkit-gngeo.deb "${PPA_POOL}/${NGDEVKIT_GNGEO}" \
 && sha256sum --check --strict ngdevkit.sha256 \
 && apt-get update --snapshot "${UBUNTU_SNAPSHOT}" \
 && apt-get install -y --no-install-recommends --snapshot "${UBUNTU_SNAPSHOT}" \
      ./ngdevkit-toolchain.deb ./ngdevkit.deb ./ngdevkit-gngeo.deb \
 && cd / && rm -rf /tmp/ngdevkit /var/lib/apt/lists/* \
 && m68k-neogeo-elf-gcc --version | head -1

WORKDIR /work
