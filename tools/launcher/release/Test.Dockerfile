# A clean desktop test image: deliberately no Python, GTK, libarchive, gcc or i386 packages.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb xauth fonts-dejavu-core libgl1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
