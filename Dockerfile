FROM ubuntu:26.04@sha256:f144425ff09be612d6d9ad965196e9cdc23dae1f42110a8a11a3e9a8198759f7 AS toolchain

ENV DEBIAN_FRONTEND=noninteractive

RUN printf 'Acquire::Retries "8";\nAcquire::http::Timeout "60";\nAcquire::https::Timeout "60";\n' > /etc/apt/apt.conf.d/80retries

ARG UBUNTU_SNAPSHOT=20261014T000000Z
ARG CA_CERTIFICATES=20260601~26.04.1
ARG PPA_POOL=https://ppa.launchpadcontent.net/dciabrin/ngdevkit/ubuntu/pool/main/n
ARG NGDEVKIT_TOOLCHAIN=ngdevkit-toolchain/ngdevkit-toolchain_0.1%2b202606181616-15%7eubuntu26.04.1_amd64.deb
ARG NGDEVKIT=ngdevkit/ngdevkit_0.5%2b202607191609-17%7eubuntu26.04.1_amd64.deb
ARG NGDEVKIT_GNGEO=ngdevkit-gngeo/ngdevkit-gngeo_0.8.1%2b202607271849-11%7eubuntu26.04.1_amd64.deb

RUN apt-get update \
 && apt-get install -y --no-install-recommends "ca-certificates=${CA_CERTIFICATES}" \
 && apt-get update --snapshot "${UBUNTU_SNAPSHOT}" \
 && apt-get install -y --no-install-recommends --snapshot "${UBUNTU_SNAPSHOT}" \
      autoconf \
      automake \
      binutils \
      cppcheck \
      curl \
      git \
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
