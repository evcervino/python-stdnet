#!/usr/bin/env python
'''Stdnet asynchronous test suite. Requires pulsar.'''
import sys
import os
## This is for dev environment with pulsar and dynts.
## If not available, some tests won't run
p = os.path
dir = p.dirname(p.dirname(p.abspath(__file__)))
try:
    import pulsar
except ImportError:
    pdir = p.join(dir, 'pulsar')
    if os.path.isdir(pdir):
        sys.path.append(pdir)
        import pulsar
from pulsar.apps.test import TestSuite
from pulsar.apps.test.plugins import bench, profile
#
try:
    import dynts
except ImportError:
    pdir = p.join(dir, 'dynts')
    if os.path.isdir(pdir):
        sys.path.append(pdir)
        try:
            import dynts
        except ImportError:
            pass

from stdnet.utils import test


def start():
    os.environ['stdnet_test_suite'] = 'pulsar'
    suite = TestSuite(
            description='Stdnet Asynchronous test suite',
                modules=('tests.py',),
                plugins=(test.StdnetPlugin(),
                         bench.BenchMark(),
                         profile.Profile())
              )
    suite.start()
    
    
if __name__ == '__main__':
    print(sys.version)
    start()