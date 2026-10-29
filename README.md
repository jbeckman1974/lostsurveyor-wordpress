# LostSurveyor WordPress

The current official `wordpress:php8.5-apache` image with **Debian `libvips-tools`** added for LostSurveyor's automatic map tiling. No other packages or changes to PHP/Apache are added deliberately; apt installs libvips' required dependencies.

GitHub Actions performs a clean build daily and on build-source changes, tests PHP, Apache, image codecs and Q80 WebP Deep Zoom tiles, then publishes verified changes to:

`ghcr.io/jbeckman1974/lostsurveyor-wordpress:latest`

Each build pulls the current official base and current Debian packages. No base digest or package revision is pinned. Unique build tags and recorded digests provide recovery references. Unchanged components leave `latest` untouched.

Portainer/Watchtower pull the finished image; no server-side rebuild is needed. This repository contains no website files, maps, database settings or credentials.

See [OPERATIONS.md](OPERATIONS.md) for tests, updates and rollback.
