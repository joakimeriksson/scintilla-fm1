#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compiler selection for Linux, Intel Macs, native ARM Macs and Rosetta."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from host_cc import host_cc


class HostCompilerTest(unittest.TestCase):
    def test_supported_hosts(self):
        cases = [
            ('linux', '', 0, ['cc']),
            ('darwin', '', 1, ['cc']),       # Intel: sysctl key does not exist
            ('darwin', '0\n', 0, ['cc']),    # native Apple Silicon
            ('darwin', '1\n', 0, ['arch', '-arm64', 'cc']),  # Rosetta Python
        ]
        for platform, stdout, returncode, expected in cases:
            with self.subTest(platform=platform, translated=stdout):
                result = subprocess.CompletedProcess([], returncode, stdout=stdout)
                with patch('host_cc.sys.platform', platform), patch('host_cc.subprocess.run', return_value=result):
                    self.assertEqual(host_cc(), expected)


if __name__ == '__main__':
    unittest.main()
