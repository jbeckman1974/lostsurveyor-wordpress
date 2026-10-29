import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'ci/image.py'
spec = importlib.util.spec_from_file_location('image', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BASE = 'sha256:' + 'a' * 64
INPUTS = 'b' * 64
IMAGE_ID = 'sha256:' + 'c' * 64
REVISION = 'd' * 40
REPORT = {'php': '8.5.12', 'apache': 'Server version: Apache/2.4.68 (Debian)',
          'vips': 'vips-8.16.1', 'packages': 'libvips42t64\t8.16.1-1+deb13u2\n',
          'codecs': ['PNG', 'JPEG', 'TIFF', 'JPEG2000', 'WebP'],
          'q80_tiles': 17, 'http_php': True}
ENV = {'GITHUB_ACTIONS': 'true', 'GITHUB_REF': 'refs/heads/main',
       'GITHUB_SHA': REVISION, 'GITHUB_RUN_ID': '123',
       'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_EVENT_NAME': 'push'}


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = {'status': 'verified', 'candidate_id': IMAGE_ID,
                     'base_digest': BASE, 'inputs_sha': INPUTS,
                     'revision': REVISION, 'verification': REPORT,
                     'fingerprint': m.signature(BASE, INPUTS, REPORT)}
        (self.root / 'release-report.json').write_text(json.dumps(self.data))
        self.calls = []

    def docker(self, *args, **kwargs):
        self.calls.append(args)
        if args[:1] == ('pull',):
            return subprocess.CompletedProcess(args, 1, '', 'manifest unknown')
        return subprocess.CompletedProcess(args, 0, 'digest: ' + BASE, '')

    def publish(self, **kwargs):
        with patch.object(m, 'ROOT', self.root), patch.dict(os.environ, ENV, clear=True), \
             patch.object(m, 'docker', kwargs.get('docker', self.docker)), \
             patch.object(m, 'inspect', return_value=kwargs.get('image', {'Id': IMAGE_ID})), \
             patch.object(m, 'read_report', return_value=kwargs.get('report', REPORT)):
            m.publish()

    def test_real_compatibility_and_geometry_requirements(self):
        self.assertEqual(m.validate(REPORT), REPORT)
        for key, value in [('php', '8.3.9'), ('vips', 'vips-9.0.0'),
                           ('q80_tiles', True), ('q80_tiles', 16),
                           ('http_php', False), ('codecs', ['WebP']),
                           ('packages', ''), ('packages', []), ('apache', 3)]:
            data = copy.deepcopy(REPORT)
            data[key] = value
            with self.subTest(key=key, value=str(value)[:30]), self.assertRaises(ValueError):
                m.validate(data)

    def test_publication_requires_verified_exact_image(self):
        with self.assertRaises(ValueError):
            self.publish(image={'Id': 'sha256:' + 'e' * 64})
        self.assertEqual(self.calls, [])

    def test_changed_report_cannot_publish(self):
        changed = {**REPORT, 'packages': 'changed\n'}
        with self.assertRaises(ValueError):
            self.publish(report=changed)
        self.assertEqual(self.calls, [])

    def test_pull_requests_cannot_publish_or_contact_docker(self):
        with patch.dict(os.environ, {**ENV, 'GITHUB_EVENT_NAME': 'pull_request'}, clear=True), \
             patch.object(m, 'docker') as docker:
            with self.assertRaises(ValueError):
                m.publish()
            docker.assert_not_called()

    def test_recovery_tag_published_before_latest(self):
        self.publish()
        pushes = [a for a in self.calls if a[0] == 'push']
        self.assertEqual(pushes, [('push', m.IMAGE + ':build-123-1'),
                                  ('push', m.IMAGE + ':latest')])
        self.assertEqual(json.loads((self.root / 'release-report.json').read_text())['status'], 'published')

    def test_failed_recovery_push_never_moves_latest(self):
        def fail(*args, **kwargs):
            if args == ('push', m.IMAGE + ':build-123-1'):
                raise RuntimeError('push failed')
            return self.docker(*args, **kwargs)
        with self.assertRaises(RuntimeError):
            self.publish(docker=fail)
        self.assertNotIn(('tag', m.CANDIDATE, m.IMAGE + ':latest'), self.calls)

    def test_unreconciled_baseline_does_not_publish(self):
        def unauthorized(*args, **kwargs):
            self.calls.append(args)
            return subprocess.CompletedProcess(args, 1, '', 'unauthorized')
        with self.assertRaises(RuntimeError):
            self.publish(docker=unauthorized)
        self.assertEqual([a[0] for a in self.calls], ['pull'])

    def test_identical_components_leave_latest_untouched(self):
        def found(*args, **kwargs):
            self.calls.append(args)
            return subprocess.CompletedProcess(args, 0, '', '')
        image = {'Id': IMAGE_ID, 'Config': {'Labels': {
            'net.lostsurveyor.image.base': BASE,
            'net.lostsurveyor.image.inputs': INPUTS}}}
        self.publish(docker=found, image=image)
        self.assertEqual([a[0] for a in self.calls], ['pull'])
        self.assertEqual(json.loads((self.root / 'release-report.json').read_text())['status'], 'unchanged')

    def test_full_debian_revision_affects_fingerprint(self):
        patched = {**REPORT, 'packages': REPORT['packages'].replace('deb13u2', 'deb13u3')}
        self.assertNotEqual(m.signature(BASE, INPUTS, REPORT), m.signature(BASE, INPUTS, patched))

    def test_build_context_and_rolling_base(self):
        root = PATH.parents[1]
        dockerfile = (root / 'Dockerfile').read_text()
        self.assertIn('FROM wordpress:php8.5-apache\n', dockerfile)
        self.assertNotIn('FROM wordpress@', dockerfile)
        self.assertEqual((root / '.dockerignore').read_text().splitlines(),
                         ['**', '!Dockerfile', '!verify.sh'])
        workflow = (root / '.github/workflows/image.yml').read_text()
        self.assertIn('persist-credentials: false', workflow)
        self.assertNotIn('self-hosted', workflow)
        self.assertNotIn('PORTAINER', workflow)

    def test_local_entrypoint_refuses_docker_work(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(m, 'docker') as docker:
            with self.assertRaises(RuntimeError):
                m.main()
            docker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
