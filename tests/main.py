#!/usr/bin/env python3
"""
Test runner script to execute all the test cases for the advanced query language.
"""
import unittest
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import test cases
from tests.test_complex_queries import TestQueryService
from tests.test_pattern_matching import TestPatternMatching
from tests.test_query_operators import TestQueryOperators


def run_tests():
    """
    Run all test cases for the advanced query language.
    """
    # Create test suite
    test_suite = unittest.TestSuite()

    # Add test cases
    test_suite.addTest(unittest.makeSuite(TestQueryService))
    test_suite.addTest(unittest.makeSuite(TestPatternMatching))
    test_suite.addTest(unittest.makeSuite(TestQueryOperators))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(test_suite)


if __name__ == "__main__":
    run_tests()
