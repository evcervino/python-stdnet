import os
import sys
import logging

from stdnet.conf import settings
from stdnet.utils.importer import import_module

from .test import TestCase, TestMultiFieldMixin, TestSuiteRunner, setup_logging
from .bench import BenchMark, BenchSuiteRunner
from .profile import ProfileTest, ProfileSuiteRunner


TEST_TYPES = {'regression': TestSuiteRunner,
              'bench': BenchSuiteRunner,
              'profile': ProfileSuiteRunner,
              'fuzzy': TestSuiteRunner}


def get_tests(test_type, tests_path):
    '''Gather tests type'''
    tests = []
    join  = os.path.join
    for dirpath in tests_path:
        dirpath = dirpath(test_type)
        loc = os.path.split(dirpath)[1]
        for d in os.listdir(dirpath):
            if os.path.isdir(join(dirpath,d)):
                yield (loc,d)


def import_tests(tags, test_type, tests_path, library = None):
    logger = logging.getLogger()
    for loc,app in get_tests(test_type, tests_path):
        if tags and app not in tags:
            logger.debug("Skipping tests for %s" % app)
            continue
        logger.debug("Try to import tests for %s" % app)
        test_module = '{0}.{1}.tests'.format(loc,app)
        if loc == 'contrib' and library:
            test_module = '{0}.{1}.{2}'.format(library,test_module,test_type)
            
        try:
            mod = import_module(test_module)
        except ImportError as e:
            logger.debug("Could not import tests for %s: %s" % (test_module,e))
            continue
        
        logger.debug("Adding tests for %s" % app)
        yield mod


def run(tests_paths, tags = None, test_type = None,
        itags = None, verbosity = 1, backend = None,
        library = None):
    '''Test Runner'''
    std = settings.DEFAULT_BACKEND
    settings.DEFAULT_BACKEND =  backend or 'redis://127.0.0.1:6379/?db=13'
    setup_logging(verbosity)
    test_type = test_type or 'regression'
    if test_type not in TEST_TYPES:
        print(('Unknown test type {0}. Must be one of {1}.'.format(test_type, ', '.join(TEST_TYPES))))
        exit()
    TestSuiteRunner = TEST_TYPES[test_type]
    if not TestSuiteRunner:
        print(('No test suite for {0}'.format(test_type)))
        exit()
    modules = import_tests(tags, test_type, tests_paths, library)
    runner  = TestSuiteRunner(verbosity = verbosity, itags = itags)
    runner.run_tests(modules)
    settings.DEFAULT_BACKEND = std
