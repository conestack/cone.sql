import sys
import unittest


def test_suite():
    from cone.sql.tests import test_users
    from cone.sql.ugm.tests import test_model

    suite = unittest.TestSuite()

    suite.addTest(unittest.findTestCases(test_users))
    suite.addTest(unittest.findTestCases(test_model))

    return suite
