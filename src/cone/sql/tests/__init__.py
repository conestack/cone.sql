import sys
import unittest


def test_suite():
    from cone.sql.tests import test_sql
    from cone.sql.tests import test_model
    from cone.sql.tests import test_acl
    from cone.sql.tests import test_ugm

    suite = unittest.TestSuite()

    suite.addTest(unittest.findTestCases(test_sql))
    suite.addTest(unittest.findTestCases(test_model))
    suite.addTest(unittest.findTestCases(test_acl))
    suite.addTest(unittest.findTestCases(test_ugm))

    try:
        from cone.sql.tests import test_cone_ugm
        suite.addTest(unittest.findTestCases(test_cone_ugm))
    except ImportError:
        pass

    return suite


def run_tests():
    from zope.testrunner.runner import Runner

    runner = Runner(found_suites=[test_suite()])
    runner.run()
    sys.exit(int(runner.failed))


if __name__ == '__main__':
    run_tests()
