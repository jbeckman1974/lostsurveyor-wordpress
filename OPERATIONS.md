# Image maintenance

The default branch builds on relevant pushes, manual Actions runs, and daily at 04:35 UTC (00:35 EDT / 23:35 EST). GitHub schedules may be delayed or disabled after prolonged inactivity in public repositories; check Actions if updates stop. Praetorian's existing Watchtower checks at 02:15 America/New_York.

The Dockerfile follows the rolling official PHP 8.5 Apache tag. `--pull --no-cache` refreshes the base and Debian package indexes. Only `libvips-tools` and its repository dependencies are installed, then apt lists are removed. It adds a nonsecret verification report to `/usr/local/share/lostsurveyor-image/verification.json`.

The build runs on GitHub-hosted Linux amd64, isolated from LostSurveyor. No Portainer key, LAN access, site credentials, Docker socket from Praetorian, live media or database is supplied to GitHub. The temporary `GITHUB_TOKEN` publishes the image; no personal access token is stored in the repository. Checkout credentials are not persisted and only Dockerfile/verify.sh enter the build context. No pull-request workflow can publish.

Tests require PHP 8.5, Apache configuration and actual HTTP PHP, mysqli/GD/DOM/POSIX/proc_open/fsync, timeout/flock/setsid/prlimit, libvips 8, PNG/JPEG/TIFF/JPEG2000/WebP round trips, and 17 geometrically validated Q80 WebP tiles for a 513×257 synthetic image (256-pixel tiles, 1-pixel overlap). These are image compatibility checks, not live WordPress/database/browser tests or a comprehensive vulnerability scan. Full Debian revisions distinguish backports from upstream versions. PHP minor/major, Apache/FPM or incompatible libvips changes need review.

The build report is retained as an Actions artifact for 90 days. A fingerprint of the resolved base, build inputs and complete package/test report avoids moving `latest` when components are unchanged. Changed verified images are published first as `build-RUNID-ATTEMPT`, then `latest`. Unique tags are retained; no image deletion/pruning is configured. If a registry push reports an uncertain result, inspect its tags/digests before manually retrying.

GHCR initially creates packages private, even for a public source repository. After the first successful publish, make this package public in GitHub package settings and verify anonymous pull before changing Portainer. Only this nonsecret base-plus-libvips image becomes public.

Portainer stack image: `ghcr.io/jbeckman1974/lostsurveyor-wordpress:latest`. Preserve the existing renderer-busy pre-update hook and UID/GID 33:33, and set the WordPress Watchtower `no-pull` label to `false`. Preserve all data mounts, settings, ports, networks, database bindings and other service images. Use only the authoritative FS-1 Portainer for stack administration; never a competing Compose deployment.

Migration order: retain the current image and protected stack export; complete a successful GitHub build; verify public pull and report/platform on Praetorian; hold/disable the old administrative build timer; update only WordPress's image and its no-pull label through Portainer; verify exact mounts/settings, database/site and public/private viewers; refresh the protected stack backup. A full stack update may recreate MySQL/Redis without changing their data or images. Do not remove old builder/rollback files while migrating. No website/plugin/map-processing configuration changes are required.

Rollback: through FS-1 Portainer, restore the previous image/stack with pulling/pruning disabled and original mounts/bindings. Existing exact-image archives remain outside the webroot. Hold automatic image updates before rollback so Watchtower cannot immediately reverse it. Recover a previous GHCR release by its recorded unique build tag/digest. Do not restore/delete site media or database data merely to change an image. Re-enable the old local builder only after restoring its compatible local stack tag/no-pull policy. Updraft does not preserve image-installed packages or every outside-webroot folder.

WordPress core/plugins in persistent site storage still have their own update mechanism; refreshing the container base does not itself upgrade an already-installed WordPress site.
