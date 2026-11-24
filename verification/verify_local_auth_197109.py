#!/usr/bin/env python3
# Copyright 2026 The Flutter Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Fork-only Windows verification; never treats infrastructure errors as a repro."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'verification-results'
PACKAGE = ROOT / 'packages/local_auth/local_auth_windows'
BASE = '5b93485c4b49318606ea4d0648203f6ec7b4aaf3'
SDK = Path(os.environ['RUNNER_TEMP']) / 'flutter-sdk'
FLUTTER = str(SDK / 'bin/flutter.bat')
DART = str(SDK / 'bin/dart.bat')
RESULTS = {'base': BASE, 'runner': os.environ.get('RUNNER_LABEL'), 'commands': []}
OUT.mkdir(exist_ok=True)

def run(name, args, cwd=ROOT):
    print(f'::group::{name}', flush=True)
    print(subprocess.list2cmdline(args), flush=True)
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    (OUT / f'{name}.log').write_text(result.stdout, encoding='utf-8')
    print(result.stdout, flush=True)
    print('::endgroup::', flush=True)
    RESULTS['commands'].append({'name': name, 'args': args, 'exit': result.returncode})
    (OUT / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')
    return result

def require(name, args, cwd=ROOT):
    result = run(name, args, cwd)
    if result.returncode:
        raise RuntimeError(f'{name} failed, exit {result.returncode}; see log')
    return result

def main():
    require('flutter-version', [FLUTTER, '--version', '--machine'])
    require('flutter-doctor', [FLUTTER, 'doctor', '-v'])
    require('tool-dependencies', [DART, 'pub', 'get'], ROOT / 'script/tool')
    require('package-dependencies', [FLUTTER, 'pub', 'get'], PACKAGE)
    require('example-dependencies', [FLUTTER, 'pub', 'get'], PACKAGE / 'example')
    # Restore only the native source files to the recorded baseline. pubspec and
    # tests are identical for the two builds. Restore the patch even on failure.
    paths = ['windows/CMakeLists.txt', 'windows/local_auth.h', 'windows/local_auth_plugin.cpp']
    patched = {p: (PACKAGE / p).read_bytes() for p in paths}
    try:
        for path in paths:
            original = subprocess.check_output(['git', 'show', f'{BASE}:packages/local_auth/local_auth_windows/{path}'], cwd=ROOT)
            (PACKAGE / path).write_bytes(original)
        baseline = run('baseline-build', [FLUTTER, 'build', 'windows', '--debug'], PACKAGE / 'example')
        if os.environ['RUNNER_LABEL'] == 'windows-2025-vs2026':
            if baseline.returncode == 0 or 'STL1011' not in baseline.stdout:
                raise RuntimeError('Expected nonzero baseline build containing STL1011; infrastructure/other failures do not count')
            RESULTS['baseline_expected_regression'] = True
        elif baseline.returncode != 0:
            raise RuntimeError('Older toolset baseline should build successfully')
    finally:
        for path, content in patched.items():
            (PACKAGE / path).write_bytes(content)
        (OUT / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')
    require('patched-build', [FLUTTER, 'build', 'windows', '--debug'], PACKAGE / 'example')
    # The repository native-test tool builds the unit_tests target in Debug.
    require('native-tests', [DART, 'run', 'script/tool/bin/flutter_plugin_tools.dart', 'native-test', '--windows', '--packages=local_auth_windows'])
    require('dart-analyze', [DART, 'run', 'script/tool/bin/flutter_plugin_tools.dart', 'analyze', '--packages=local_auth_windows'])
    require('dart-tests', [DART, 'run', 'script/tool/bin/flutter_plugin_tools.dart', 'test', '--packages=local_auth_windows'])
    require('metadata-validation', [DART, 'run', 'script/tool/bin/flutter_plugin_tools.dart', 'validate', '--check-for-missing-changes', '--packages=local_auth_windows'])
    require('diff-check', ['git', 'diff', '--check'])
    require('source-restored', ['git', 'diff', '--exit-code', '--', 'packages/local_auth/local_auth_windows'])
    RESULTS['complete'] = True
    (OUT / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
