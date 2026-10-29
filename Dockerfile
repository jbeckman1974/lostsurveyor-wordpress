# Always pull the current official PHP 8.5 Apache image; no fixed digest/version.
FROM wordpress:php8.5-apache

RUN timeout 900 /bin/sh -c 'apt-get update \
    && apt-get install -y --no-install-recommends libvips-tools \
    && rm -rf /var/lib/apt/lists/*'

COPY verify.sh /tmp/lsnt-verify.sh
RUN mkdir -p /usr/local/share/lostsurveyor-image \
    && timeout 120 /bin/sh /tmp/lsnt-verify.sh

ARG BASE_DIGEST
ARG INPUTS_SHA
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/jbeckman1974/lostsurveyor-wordpress" \
      org.opencontainers.image.description="Official WordPress PHP 8.5 Apache plus Debian libvips; codec and Q80 DZI tests required" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      net.lostsurveyor.image.base="${BASE_DIGEST}" \
      net.lostsurveyor.image.inputs="${INPUTS_SHA}"
