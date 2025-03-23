import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Adjust path to import from src directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.services.query_service import QueryService
from src.db.models import (
    Module,
    Function,
    WhereFunction,
    Import,
    Type,
    Constructor,
    Field,
    Class,
    Instance,
    InstanceFunction,
    function_dependency,
)
from src.db.connection import Base


class TestQueryService(unittest.TestCase):
    """Test cases for the query service and advanced query language."""

    @classmethod
    def setUpClass(cls):
        """Set up the in-memory database for testing."""
        # Create in-memory SQLite database with a unique URI to ensure a fresh database
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        cls.Session = sessionmaker(bind=cls.engine)

        # Create all tables
        Base.metadata.create_all(cls.engine)

    def setUp(self):
        """Set up test data before each test."""
        self.session = self.Session()
        self.query_service = QueryService(self.session)

        # Start a transaction that can be rolled back
        self.transaction = self.connection = self.engine.connect()
        self.trans = self.connection.begin()

        # Create test data
        self._create_test_data()

    def tearDown(self):
        """Clean up after each test."""
        self.session.query(function_dependency).delete()
        self.session.query(WhereFunction).delete()
        self.session.query(Function).delete()
        self.session.query(Type).delete()
        self.session.query(Import).delete()
        self.session.query(Class).delete()
        self.session.query(Module).delete()

        self.session.commit()
        self.session.close()

    def _create_test_data(self):
        """Create test data for the database."""
        # Create modules without specifying IDs - let SQLAlchemy handle it
        module1 = Module(name="app.core", path="app/core")
        module2 = Module(name="app.util", path="app/util")
        module3 = Module(name="app.handlers", path="app/handlers")

        self.session.add_all([module1, module2, module3])
        self.session.flush()  # Flush to get the assigned IDs

        # Create functions with dynamically assigned module IDs
        function1 = Function(
            name="processData",
            function_signature="Data -> Result",
            raw_string="processData = \\data -> transformData data",
            src_loc="app/core/data.hs:10",
            line_number_start=10,
            line_number_end=15,
            type_enum="function",
            module_id=module1.id,
        )

        function2 = Function(
            name="validateInput",
            function_signature="Input -> Bool",
            raw_string="validateInput = \\input -> checkFormat input && checkContent input",
            src_loc="app/util/validation.hs:25",
            line_number_start=25,
            line_number_end=30,
            type_enum="function",
            module_id=module2.id,
        )

        function3 = Function(
            name="requestHandler",
            function_signature="Request -> Response",
            raw_string="""requestHandler req = do
                case validateInput req of
                    True -> processData req
                    False -> errorResponse
                where
                    errorResponse = Response 400 "Invalid input"
            """,
            src_loc="app/handlers/request.hs:40",
            line_number_start=40,
            line_number_end=50,
            type_enum="function",
            module_id=module3.id,
        )

        function4 = Function(
            name="utilityFunction",
            function_signature="String -> String",
            raw_string="utilityFunction = id",
            src_loc="app/util/common.hs:5",
            line_number_start=5,
            line_number_end=7,
            type_enum="function",
            module_id=module2.id,
        )

        function5 = Function(
            name="dataHandler",
            function_signature="Data -> IO ()",
            raw_string="""dataHandler d = do
                let result = processData d
                saveResult result
                logActivity "Data processed"
            """,
            src_loc="app/handlers/data.hs:20",
            line_number_start=20,
            line_number_end=30,
            type_enum="function",
            module_id=module3.id,
        )

        self.session.add_all([function1, function2, function3, function4, function5])
        self.session.flush()

        # Create where functions
        where_function1 = WhereFunction(
            name="errorResponse",
            function_signature="Response",
            raw_string='errorResponse = Response 400 "Invalid input"',
            src_loc="app/handlers/request.hs:46",
            parent_function_id=function3.id,
        )

        self.session.add(where_function1)
        self.session.flush()

        # Create function dependencies
        self.session.execute(
            function_dependency.insert().values(
                caller_id=function3.id, callee_id=function2.id
            )
        )  # requestHandler calls validateInput

        self.session.execute(
            function_dependency.insert().values(
                caller_id=function3.id, callee_id=function1.id
            )
        )  # requestHandler calls processData

        self.session.execute(
            function_dependency.insert().values(
                caller_id=function5.id, callee_id=function1.id
            )
        )  # dataHandler calls processData

        # Create types
        type1 = Type(
            type_name="Data",
            raw_code="data Data = Data { field1 :: String, field2 :: Int }",
            src_loc="app/core/types.hs:5",
            type_of_type="data",
            line_number_start=5,
            line_number_end=8,
            module_id=module1.id,
        )

        type2 = Type(
            type_name="Response",
            raw_code="data Response = Response { status :: Int, message :: String }",
            src_loc="app/handlers/types.hs:10",
            type_of_type="data",
            line_number_start=10,
            line_number_end=13,
            module_id=module3.id,
        )

        self.session.add_all([type1, type2])
        self.session.flush()

        # Create imports
        import1 = Import(
            module_name="app.core",
            src_loc="app/handlers/request.hs:1",
            line_number_start=1,
            line_number_end=1,
            module_id=module3.id,
        )

        import2 = Import(
            module_name="app.util",
            src_loc="app/handlers/request.hs:2",
            line_number_start=2,
            line_number_end=2,
            module_id=module3.id,
        )

        self.session.add_all([import1, import2])
        self.session.flush()

        # Create classes
        class1 = Class(
            class_name="Processable",
            class_definition="class Processable a where process :: a -> Result",
            src_location="app/core/classes.hs:15",
            line_number_start=15,
            line_number_end=18,
            module_id=module1.id,
        )

        self.session.add(class1)

        # Commit all test data
        self.session.commit()

    def test_simple_function_query(self):
        """Test a simple query to get functions by name."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "eq", "value": "processData"}],
        }

        results = self.query_service.execute_advanced_query(query)
        print([i.__dict__ for i in results])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "processData")
        self.assertEqual(results[0].module_id, 1)

    def test_like_operator(self):
        """Test using the LIKE operator to find functions with partial name match."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "like", "value": "%Handler%"}],
        }

        results = self.query_service.execute_advanced_query(query)

        self.assertEqual(len(results), 2)
        function_names = [f.name for f in results]
        self.assertIn("requestHandler", function_names)
        self.assertIn("dataHandler", function_names)

    def test_multiple_conditions(self):
        """Test query with multiple conditions."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "like", "value": "%Handler%"},
                {"field": "module_id", "operator": "eq", "value": 3},
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].module_id, 3)
        self.assertEqual(results[1].module_id, 3)

    def test_contains_operator(self):
        """Test using the contains operator for raw string search."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "raw_string", "operator": "contains", "value": "case"}
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "requestHandler")

    def test_function_call_relationship(self):
        """Test finding function call relationships."""

        # First, find the ID of the processData function
        processData = self.session.query(Function).filter_by(name="processData").first()

        if not processData:
            self.fail("processData function not found in test data")

        # Print helpful debug info
        print(f"Looking for functions that call processData (ID: {processData.id})")

        # Check the function_dependency table directly to confirm relationships exist
        deps = (
            self.session.query(function_dependency)
            .filter_by(callee_id=processData.id)
            .all()
        )
        print(f"Dependencies in database: {deps}")
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "eq", "value": "processData"}],
            "joins": [
                {
                    "type": "calling_function",  # Functions that call processData
                    "conditions": [],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)
        # Print what was found for debugging
        print(f"Found {len(results)} calling functions:")
        for res in results:
            print(f"  - {res.name} (ID: {res.id})")

        # Both requestHandler and dataHandler call processData
        self.assertEqual(len(results), 2)
        function_names = sorted([f.name for f in results])
        self.assertEqual(function_names, ["dataHandler", "requestHandler"])

    def test_module_function_relationship(self):
        """Test finding functions in a specific module."""
        query = {
            "type": "module",
            "conditions": [
                {"field": "name", "operator": "eq", "value": "app.handlers"}
            ],
            "joins": [{"type": "function", "conditions": []}],
        }

        results = self.query_service.execute_advanced_query(query)

        # We should get the functions in the app.handlers module
        function_names = [f.name for f in results]
        self.assertIn("requestHandler", function_names)
        self.assertIn("dataHandler", function_names)

    def test_complex_nested_query(self):
        """Test a complex query with nested joins."""
        query = {
            "type": "module",
            "conditions": [{"field": "name", "operator": "eq", "value": "app.core"}],
            "joins": [
                {
                    "type": "function",
                    "conditions": [],
                    "joins": [
                        {
                            "type": "calling_function",  # Functions that call functions in app.core
                            "conditions": [
                                {
                                    "field": "module_id",
                                    "operator": "eq",
                                    "value": 3,
                                }  # From app.handlers module
                            ],
                        }
                    ],
                }
            ],
        }

        try:
            results = self.query_service.execute_advanced_query(query)
            function_names = [f.name for f in results]
            print(function_names)
            self.assertEqual(len(results), 2)
            query_executed = True
        except Exception as e:
            print(e)
            query_executed = False

        self.assertTrue(query_executed)

    def test_where_function_relationship(self):
        """Test finding functions with where functions."""
        query = {
            "type": "function",
            "conditions": [],
            "joins": [{"type": "where_function", "conditions": []}],
        }

        results = self.query_service.execute_advanced_query(query)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "requestHandler")

    def test_pattern_match_function_call(self):
        """Test pattern matching for function calls."""
        pattern = {
            "type": "function_call",
            "caller": "Handler",  # Functions with "Handler" in name
            "callee": "processData",  # That call processData
            "mode": "calls",
        }

        matches = self.query_service.pattern_match(pattern)

        self.assertEqual(len(matches), 2)  # Both handler functions call processData

        # Verify the matches contain the expected functions
        caller_names = []
        callee_names = []

        for match in matches:
            caller_names.append(match["caller"]["name"])
            callee_names.append(match["callee"]["name"])

        self.assertIn("requestHandler", caller_names)
        self.assertIn("dataHandler", caller_names)
        self.assertEqual(callee_names.count("processData"), 2)

    def test_pattern_match_called_by(self):
        """Test pattern matching for 'called by' relationships."""
        pattern = {
            "type": "function_call",
            "caller": "Handler",  # Functions with "Handler" in name
            "callee": "validateInput",  # That call validateInput
            "mode": "calls",
        }

        matches = self.query_service.pattern_match(pattern)

        self.assertEqual(len(matches), 1)  # Only requestHandler calls validateInput
        self.assertEqual(matches[0]["caller"]["name"], "requestHandler")
        self.assertEqual(matches[0]["callee"]["name"], "validateInput")

    def test_find_complex_functions(self):
        """Test finding complex functions based on metrics."""
        # We'll set a low threshold to match our test data
        complex_functions = self.query_service.find_complex_functions(
            complexity_threshold=3
        )

        # requestHandler is the most complex function in our test data
        self.assertTrue(len(complex_functions) > 0)
        found_request_handler = False

        for func in complex_functions:
            if func["function"]["name"] == "requestHandler":
                found_request_handler = True
                break

        self.assertTrue(found_request_handler)

    def test_between_operator(self):
        """Test using the between operator for numeric ranges."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "between", "value": [20, 40]}
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        self.assertEqual(len(results), 3)
        line_numbers = [f.line_number_start for f in results]
        self.assertIn(25, line_numbers)
        self.assertIn(20, line_numbers)
        self.assertIn(40, line_numbers)

    def test_in_operator(self):
        """Test using the in operator for multiple values."""
        query = {
            "type": "function",
            "conditions": [
                {
                    "field": "name",
                    "operator": "in",
                    "value": ["processData", "validateInput"],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        self.assertEqual(len(results), 2)
        function_names = [f.name for f in results]
        self.assertIn("processData", function_names)
        self.assertIn("validateInput", function_names)

    def test_cross_module_dependencies(self):
        """Test finding cross-module dependencies."""
        dependencies = self.query_service.find_cross_module_dependencies()

        # We should have dependencies from app.handlers to app.core and app.util
        self.assertTrue(len(dependencies) >= 2)

        # Convert to a more easily testable format
        dep_map = {}
        for dep in dependencies:
            caller = dep["caller_module"]["name"]
            callee = dep["callee_module"]["name"]
            key = f"{caller}->{callee}"
            dep_map[key] = dep["call_count"]

        # Check for expected dependencies
        self.assertIn("app.handlers->app.core", dep_map)
        self.assertIn("app.handlers->app.util", dep_map)


if __name__ == "__main__":
    unittest.main()
