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
from tests.test_rust_complex_queries import TestRustComplexQueries
from tests.test_rust_pattern_matching import TestRustPatternMatching
from tests.test_rust_query_operators import TestRustQueryOperators


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
    test_suite.addTest(unittest.makeSuite(TestRustComplexQueries))
    test_suite.addTest(unittest.makeSuite(TestRustPatternMatching))
    test_suite.addTest(unittest.makeSuite(TestRustQueryOperators))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(test_suite)


if __name__ == "__main__":
    run_tests()
