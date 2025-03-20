import unittest
from sqlalchemy.orm import Session

from src.db.connection import SessionLocal
from src.services.query_service import QueryService
from src.db.models import (
    Module as DBModule,
    Function as DBFunction,
)


class TestFunctionCallRelationships(unittest.TestCase):
    """Test case for function call relationships in complex queries."""

    @classmethod
    def setUpClass(cls):
        """Set up query service with the actual database."""
        cls.db = SessionLocal()
        cls.query_service = QueryService(cls.db)

    @classmethod
    def tearDownClass(cls):
        """Close database connection."""
        cls.db.close()

    def test_find_calling_functions(self):
        """Find all functions that call a specific function."""
        # First get a function that is likely called by other functions
        utility_functions = self.query_service.execute_advanced_query(
            {
                "type": "function",
                "conditions": [
                    {"field": "name", "operator": "eq", "value": "setLoggerContext"}
                ],
            }
        )

        if not utility_functions:
            # Try another common function
            utility_functions = self.query_service.execute_advanced_query(
                {
                    "type": "function",
                    "conditions": [
                        {"field": "name", "operator": "like", "value": "%getLogger%"}
                    ],
                }
            )

        if not utility_functions:
            self.skipTest("No suitable utility functions found for test")
            return

        # Choose the first utility function
        utility_function = utility_functions[0]

        print(f"Testing with utility function: {utility_function.name}")

        # Now find all functions that call this function using the query language
        query = {
            "type": "function",
            "joins": [
                {
                    "type": "called_function",
                    "conditions": [
                        {"field": "id", "operator": "eq", "value": utility_function.id}
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        print(f"Found {len(results)} functions that call {utility_function.name}")
        for i, func in enumerate(results[:5]):  # Print first 5 results
            print(f"{i+1}. {func.name}")

        self.assertIsInstance(results, list)

    def test_find_functions_called_by_specific_function(self):
        """Find all functions that are called by a specific function."""
        # First get a function that likely calls other functions
        candidate_functions = self.query_service.execute_advanced_query(
            {
                "type": "function",
                "conditions": [
                    {"field": "name", "operator": "like", "value": "%process%"}
                ],
            }
        )

        if not candidate_functions:
            self.skipTest("No suitable functions found for test")
            return

        # Choose the first candidate function
        caller_function = candidate_functions[0]

        # Get details to see if it calls other functions
        details = self.query_service.get_function_details(caller_function.id)
        if not details or not details.get("calls"):
            self.skipTest(
                f"Function {caller_function.name} doesn't call other functions"
            )
            return

        print(f"Testing with caller function: {caller_function.name}")

        # Now find all functions called by this function using the query language
        query = {
            "type": "function",
            "conditions": [],
            "joins": [
                {
                    "type": "calling_function",  # Using our internal name
                    "conditions": [
                        {"field": "id", "operator": "eq", "value": caller_function.id}
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        print(f"Found {len(results)} functions called by {caller_function.name}")
        for i, func in enumerate(results[:5]):  # Print first 5 results
            print(f"{i+1}. {func.name}")

        self.assertIsInstance(results, list)
        # Compare with what we get from get_function_details
        self.assertEqual(len(results), len(details["calls"]))

    def test_find_functions_called_by_functions_in_module(self):
        """Find all functions that are called by any function in a specific module."""
        # Get a module that likely has functions calling other functions
        modules = self.query_service.get_all_modules()
        if not modules:
            self.skipTest("No modules found for test")
            return

        target_module = None
        for module in modules:
            if "oltp" in module.name.lower():
                target_module = module
                break

        if not target_module:
            target_module = modules[0]  # Fallback to first module

        print(f"Testing with module: {target_module.name}")

        # Find all functions called by any function in this module
        query = {
            "type": "function",
            "conditions": [],
            "joins": [
                {
                    "type": "calling_function",  # Using our internal name
                    "conditions": [],
                    "joins": [
                        {
                            "type": "module",
                            "conditions": [
                                {
                                    "field": "id",
                                    "operator": "eq",
                                    "value": target_module.id,
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        print(
            f"Found {len(results)} functions called by functions in module {target_module.name}"
        )
        for i, func in enumerate(results[:5]):  # Print first 5 results
            print(f"{i+1}. {func.name}")

        self.assertIsInstance(results, list)

    def test_pattern_match_with_called_by(self):
        """Test the pattern matching with called_by mode."""
        # Look for functions that are called by error handlers
        pattern = {
            "type": "function_call",
            "caller": "error",  # Functions with "error" in name
            "callee": "",  # Any function called by these error functions
            "mode": "called_by",  # Use called_by mode
        }

        results = self.query_service.pattern_match(pattern)

        print(f"Found {len(results)} functions called by error handlers")
        for i, result in enumerate(results[:5]):  # Print first 5 results
            callee = result["callee"]["name"]
            caller = result["caller"]["name"]
            print(f"{i+1}. {callee} is called by {caller}")

        self.assertIsInstance(results, list)

    def test_find_most_called_functions(self):
        """Find the most frequently called functions across the codebase."""
        most_called = self.query_service.get_most_called_functions(limit=10)

        print("Top 10 most called functions:")
        for i, func in enumerate(most_called):
            name = func["name"]
            module = func["module"]
            calls = func["calls"]
            print(f"{i+1}. {name} ({module}) - called {calls} times")

        self.assertIsInstance(most_called, list)
        self.assertLessEqual(len(most_called), 10)

    def test_find_common_utility_functions(self):
        """Find utility functions that are called by many different modules."""
        # First get the most called functions
        most_called = self.query_service.get_most_called_functions(limit=20)

        # Then for each function, count how many different modules call it
        utility_functions = []
        for func in most_called:
            # Get the functions that call this function
            pattern = {"type": "function_call", "callee": func["name"], "caller": None}

            callers = self.query_service.pattern_match(pattern)

            # Count unique modules
            caller_modules = set()
            for result in callers:
                if result["caller"]["module"]:
                    caller_modules.add(result["caller"]["module"])

            if len(caller_modules) > 1:  # Called by multiple modules
                utility_functions.append(
                    {
                        "function_name": func["name"],
                        "module": func["module"],
                        "call_count": func["calls"],
                        "module_count": len(caller_modules),
                    }
                )

        # Sort by the number of modules that call this function
        utility_functions.sort(key=lambda x: x["module_count"], reverse=True)

        print("Top utility functions used across modules:")
        for i, func in enumerate(utility_functions[:10]):  # Print top 10
            name = func["function_name"]
            calls = func["call_count"]
            modules = func["module_count"]
            print(
                f"{i+1}. {name} - called {calls} times from {modules} different modules"
            )

        self.assertIsInstance(utility_functions, list)


if __name__ == "__main__":
    unittest.main()
