# SPDX-License-Identifier: GPL-3.0-only
"""Select the native host compiler, including Python running under Rosetta."""
import subprocess
import sys


def host_cc():
    if sys.platform == 'darwin':
        translated = subprocess.run(['sysctl', '-n', 'sysctl.proc_translated'],
                                    capture_output=True, text=True).stdout.strip()
        if translated == '1':
            return ['arch', '-arm64', 'cc']
    return ['cc']
