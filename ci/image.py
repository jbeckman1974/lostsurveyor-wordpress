#!/usr/bin/env python3
"""GitHub-hosted build/publish only. No Portainer, site data or host daemon use."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = 'wordpress:php8.5-apache'
IMAGE = 'ghcr.io/jbeckman1974/lostsurveyor-wordpress'
CANDIDATE = 'lostsurveyor-ci:verified'
REPORT_PATH = '/usr/local/share/lostsurveyor-image/verification.json'
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')


def docker(*args, timeout=900, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True,
                            timeout=timeout, cwd=ROOT)
    if len(result.stdout) + len(result.stderr) > 8 * 1024 * 1024:
        raise RuntimeError('Unexpectedly large Docker response')
    if check and result.returncode:
        # Only official image/build output, never authentication commands/env.
        raise RuntimeError('Docker operation failed:\n' +
                           (result.stdout + result.stderr)[-8000:])
    return result


def inspect(ref):
    return json.loads(docker('image', 'inspect', ref).stdout)[0]


def validate(data):
    if not isinstance(data, dict) or set(data) != {
        'php', 'apache', 'vips', 'packages', 'codecs', 'q80_tiles', 'http_php'
    }:
        raise ValueError('Invalid verification report fields')
    if (not isinstance(data['php'], str) or
        not re.fullmatch(r'8\.5\.\d+', data['php']) or
        not isinstance(data['vips'], str) or
        not re.fullmatch(r'vips-8\.\d+\.\d+', data['vips']) or
        not isinstance(data['apache'], str) or
        'Apache/2.4.' not in data['apache'] or
        not isinstance(data['packages'], str) or
        not 1 <= len(data['packages']) <= 1024 * 1024 or
        data['codecs'] != ['PNG', 'JPEG', 'TIFF', 'JPEG2000', 'WebP'] or
        type(data['q80_tiles']) is not int or data['q80_tiles'] != 17 or
        data['http_php'] is not True):
        raise ValueError('Image compatibility/self-test requirements not met')
    return data


def read_report(ref):
    raw = docker('run', '--rm', '--network=none', '--read-only',
                 '--cap-drop=ALL', '--security-opt=no-new-privileges',
                 '--pids-limit=32', '--memory=32m', '--cpus=1',
                 '--entrypoint=/bin/cat', ref, REPORT_PATH, timeout=30).stdout
    return validate(json.loads(raw))


def signature(base, inputs, report):
    if not DIGEST.fullmatch(base) or not re.fullmatch(r'[0-9a-f]{64}', inputs):
        raise ValueError('Invalid source identity')
    validate(report)
    return hashlib.sha256(json.dumps({
        'base': base, 'inputs': inputs, 'report': report
    }, sort_keys=True).encode()).hexdigest()


def save(data):
    (ROOT / 'release-report.json').write_text(json.dumps(data, indent=2) + '\n')


def build():
    docker('pull', '--platform=linux/amd64', OFFICIAL)
    base = inspect(OFFICIAL)
    digests = {s.split('@', 1)[1] for s in base.get('RepoDigests', [])
               if s.split('@', 1)[0] in ('wordpress', 'docker.io/library/wordpress')}
    if len(digests) != 1:
        raise ValueError('Ambiguous official base digest')
    digest = digests.pop()
    inputs = hashlib.sha256(b'\0'.join(
        (ROOT / p).read_bytes() for p in ['Dockerfile', 'verify.sh', '.dockerignore']
    )).hexdigest()
    revision = os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Invalid source revision')
    built = docker('build', '--platform=linux/amd64', '--pull', '--no-cache', '--progress=plain',
           '--build-arg=BASE_DIGEST=' + digest,
           '--build-arg=INPUTS_SHA=' + inputs,
           '--build-arg=SOURCE_REVISION=' + revision,
           '--tag=' + CANDIDATE, '.', timeout=1800)
    # BuildKit reports the base actually resolved by FROM. If the rolling tag
    # changed between the initial pull and build, hold rather than mislabel it.
    actual = set(re.findall(r'FROM (?:docker.io/library/)?wordpress:php8\.5-apache@'
                            r'(sha256:[0-9a-f]{64})', built.stdout + built.stderr))
    if actual != {digest}:
        raise ValueError('Actual build base differs from recorded official base')
    image = inspect(CANDIDATE)
    if image.get('Architecture') != 'amd64' or image.get('Os') != 'linux':
        raise ValueError('Unexpected image platform')
    labels = image['Config'].get('Labels') or {}
    if (labels.get('net.lostsurveyor.image.base') != digest or
        labels.get('net.lostsurveyor.image.inputs') != inputs):
        raise ValueError('Build identity mismatch')
    report = read_report(CANDIDATE)
    save({'status': 'verified', 'candidate_id': image['Id'],
          'base_digest': digest, 'base_image_id': base['Id'], 'inputs_sha': inputs,
          'revision': revision, 'verification': report,
          'fingerprint': signature(digest, inputs, report)})
    print('Verified PHP/Apache, five codecs and 17 Q80 WebP DZI tiles.')


def publish():
    if (os.environ.get('GITHUB_REF') != 'refs/heads/main' or
        os.environ.get('GITHUB_EVENT_NAME') not in ('push', 'schedule', 'workflow_dispatch')):
        raise ValueError('Publishing is restricted to trusted main-branch events')
    data = json.loads((ROOT / 'release-report.json').read_text())
    if (data['status'] != 'verified' or inspect(CANDIDATE)['Id'] != data['candidate_id'] or
        data['revision'] != os.environ['GITHUB_SHA'] or
        read_report(CANDIDATE) != data['verification'] or
        signature(data['base_digest'], data['inputs_sha'], data['verification']) != data['fingerprint']):
        raise ValueError('Verified candidate identity changed')
    previous = docker('pull', IMAGE + ':latest', check=False)
    if previous.returncode == 0:
        old = inspect(IMAGE + ':latest')
        labels = old['Config'].get('Labels') or {}
        prior = signature(labels.get('net.lostsurveyor.image.base', ''),
                          labels.get('net.lostsurveyor.image.inputs', ''),
                          read_report(IMAGE + ':latest'))
        data['previous_image_id'] = old['Id']
        if prior == data['fingerprint']:
            data['status'] = 'unchanged'
            save(data)
            print('Base, packages and build inputs unchanged; latest left untouched.')
            return
    elif not re.search(r'manifest unknown|not found|name unknown',
                       previous.stdout + previous.stderr, re.I):
        raise RuntimeError('Cannot reconcile prior registry image; no publication attempted')
    run = os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    if not re.fullmatch(r'\d+-\d+', run):
        raise ValueError('Invalid workflow run identity')
    unique = IMAGE + ':build-' + run
    docker('tag', CANDIDATE, unique)
    docker('push', unique)
    # Retain a unique registry recovery reference BEFORE moving latest.
    docker('tag', CANDIDATE, IMAGE + ':latest')
    result = docker('push', IMAGE + ':latest')
    matches = re.findall(r'digest: (sha256:[0-9a-f]{64})', result.stdout + result.stderr)
    if len(set(matches)) != 1:
        raise RuntimeError('Publication response uncertain; inspect GHCR before retrying')
    data.update(status='published', image=IMAGE + ':latest', recovery_tag=unique,
                registry_digest=matches[0])
    save(data)
    print('Published verified image:', IMAGE + ':latest', matches[0])


def main():
    # Do not let a copied CI entry point become an alternate local Docker manager.
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Run this only on the GitHub-hosted workflow runner')
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['build', 'publish'])
    args = parser.parse_args()
    (build if args.mode == 'build' else publish)()


if __name__ == '__main__':
    main()
