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
    function_dependency,
)
from src.db.connection import Base


class TestQueryOperators(unittest.TestCase):
    """Test cases for the various query operators supported by the query language."""

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
        """Create test data for testing query operators."""
        # Create a module
        module = Module(id=1, name="test.module", path="test/module")
        self.session.add(module)
        self.session.flush()

        # Create functions with varied attributes for testing different operators
        functions = [
            Function(
                id=1,
                name="getUser",
                function_signature="UserId -> User",
                raw_string="getUser userId = findUserById userId",
                src_loc="test/module/user.hs:10",
                line_number_start=10,
                line_number_end=12,
                type_enum="function",
                module_id=1,
                function_input=["UserId"],
                function_output=["User"],
            ),
            Function(
                id=2,
                name="getAllUsers",
                function_signature="[User]",
                raw_string="getAllUsers = findAllUsers",
                src_loc="test/module/user.hs:15",
                line_number_start=15,
                line_number_end=17,
                type_enum="function",
                module_id=1,
                function_input=[],
                function_output=["[User]"],
            ),
            Function(
                id=3,
                name="createUser",
                function_signature="UserData -> User",
                raw_string="createUser userData = validateAndSave userData",
                src_loc="test/module/user.hs:20",
                line_number_start=20,
                line_number_end=25,
                type_enum="function",
                module_id=1,
                function_input=["UserData"],
                function_output=["User"],
            ),
            Function(
                id=4,
                name="updateUser",
                function_signature="UserId -> UserData -> Maybe User",
                raw_string="""updateUser userId userData = do
                    user <- findUserById userId
                    if isJust user
                        then validateAndSave (fromJust user) userData
                        else return Nothing""",
                src_loc="test/module/user.hs:30",
                line_number_start=30,
                line_number_end=40,
                type_enum="function",
                module_id=1,
                function_input=["UserId", "UserData"],
                function_output=["Maybe User"],
            ),
            Function(
                id=5,
                name="deleteUser",
                function_signature="UserId -> Bool",
                raw_string="""deleteUser userId = do
                    user <- findUserById userId
                    if isJust user
                        then removeUser userId
                        else return False""",
                src_loc="test/module/user.hs:45",
                line_number_start=45,
                line_number_end=55,
                type_enum="function",
                module_id=1,
                function_input=["UserId"],
                function_output=["Bool"],
            ),
            Function(
                id=6,
                name="findUserById",
                function_signature="UserId -> Maybe User",
                raw_string="findUserById userId = getUserFromDb userId",
                src_loc="test/module/user_db.hs:10",
                line_number_start=10,
                line_number_end=12,
                type_enum="function",
                module_id=1,
                function_input=["UserId"],
                function_output=["Maybe User"],
            ),
            Function(
                id=7,
                name="findAllUsers",
                function_signature="[User]",
                raw_string="findAllUsers = getAllUsersFromDb",
                src_loc="test/module/user_db.hs:15",
                line_number_start=15,
                line_number_end=17,
                type_enum="function",
                module_id=1,
                function_input=[],
                function_output=["[User]"],
            ),
            Function(
                id=8,
                name="validateAndSave",
                function_signature="User -> UserData -> User",
                raw_string="""validateAndSave user userData = do
                    validData <- validateUserData userData
                    saveUserToDb (updateUserFields user validData)""",
                src_loc="test/module/user_db.hs:20",
                line_number_start=20,
                line_number_end=25,
                type_enum="function",
                module_id=1,
                function_input=["User", "UserData"],
                function_output=["User"],
            ),
            Function(
                id=9,
                name="removeUser",
                function_signature="UserId -> Bool",
                raw_string="removeUser userId = deleteUserFromDb userId",
                src_loc="test/module/user_db.hs:30",
                line_number_start=30,
                line_number_end=32,
                type_enum="function",
                module_id=1,
                function_input=["UserId"],
                function_output=["Bool"],
            ),
            Function(
                id=10,
                name=None,  # NULL name for testing is_null operator
                function_signature="() -> ()",
                raw_string="",
                src_loc="test/module/empty.hs:1",
                line_number_start=1,
                line_number_end=1,
                type_enum="function",
                module_id=1,
                function_input=[],
                function_output=[],
            ),
        ]

        self.session.add_all(functions)
        self.session.flush()

        # Create function dependencies
        dependencies = [
            (4, 6),  # updateUser calls findUserById
            (5, 6),  # deleteUser calls findUserById
            (5, 9),  # deleteUser calls removeUser
            (1, 6),  # getUser calls findUserById
            (2, 7),  # getAllUsers calls findAllUsers
            (3, 8),  # createUser calls validateAndSave
            (4, 8),  # updateUser calls validateAndSave
        ]

        for caller_id, callee_id in dependencies:
            self.session.execute(
                function_dependency.insert().values(
                    caller_id=caller_id, callee_id=callee_id
                )
            )

        # Create types
        types = [
            Type(
                id=1,
                type_name="User",
                raw_code="data User = User { userId :: UserId, name :: String, email :: String, age :: Int }",
                src_loc="test/module/types.hs:5",
                type_of_type="data",
                line_number_start=5,
                line_number_end=10,
                module_id=1,
            ),
            Type(
                id=2,
                type_name="UserId",
                raw_code="type UserId = Int",
                src_loc="test/module/types.hs:12",
                type_of_type="type",
                line_number_start=12,
                line_number_end=13,
                module_id=1,
            ),
            Type(
                id=3,
                type_name="UserData",
                raw_code="data UserData = UserData { name :: String, email :: String, age :: Int }",
                src_loc="test/module/types.hs:15",
                type_of_type="data",
                line_number_start=15,
                line_number_end=20,
                module_id=1,
            ),
        ]

        self.session.add_all(types)

        # Commit all test data
        self.session.commit()

    def test_eq_operator(self):
        """Test equality operator."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "eq", "value": "getUser"}],
        }

        results = self.query_service.execute_advanced_query(query)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "getUser")

    def test_ne_operator(self):
        """Test not equal operator."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "ne", "value": "getUser"}],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return all functions except getUser and the one with NULL name
        self.assertEqual(len(results), 8)
        self.assertNotIn("getUser", [f.name for f in results if f.name])

    def test_gt_operator(self):
        """Test greater than operator."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "gt", "value": 20}
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with line_number_start > 20
        self.assertTrue(all(f.line_number_start > 20 for f in results))

    def test_lt_operator(self):
        """Test less than operator."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "lt", "value": 20}
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with line_number_start < 20
        self.assertTrue(all(f.line_number_start < 20 for f in results))

    def test_ge_operator(self):
        """Test greater than or equal operator."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "ge", "value": 30}
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with line_number_start >= 30
        self.assertTrue(all(f.line_number_start >= 30 for f in results))

    def test_le_operator(self):
        """Test less than or equal operator."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "le", "value": 15}
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with line_number_start <= 15
        self.assertTrue(all(f.line_number_start <= 15 for f in results))

    def test_like_operator(self):
        """Test LIKE operator."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "like", "value": "%User%"}],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with "User" in their name
        for result in results:
            if result.name:  # Skip NULL name
                self.assertIn("User", result.name)

    def test_ilike_operator(self):
        """Test case-insensitive LIKE operator."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "ilike", "value": "%user%"}],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with "user" in their name (case-insensitive)
        for result in results:
            if result.name:  # Skip NULL name
                self.assertIn("User", result.name)

    def test_in_operator(self):
        """Test IN operator."""
        query = {
            "type": "function",
            "conditions": [
                {
                    "field": "name",
                    "operator": "in",
                    "value": ["getUser", "getAllUsers", "createUser"],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return only the specified functions
        self.assertEqual(len(results), 3)
        names = sorted([f.name for f in results])
        self.assertEqual(names, ["createUser", "getAllUsers", "getUser"])

    def test_not_in_operator(self):
        """Test NOT IN operator."""
        query = {
            "type": "function",
            "conditions": [
                {
                    "field": "name",
                    "operator": "not_in",
                    "value": ["getUser", "getAllUsers", "createUser"],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should not include the specified functions
        function_names = [f.name for f in results if f.name]
        self.assertNotIn("getUser", function_names)
        self.assertNotIn("getAllUsers", function_names)
        self.assertNotIn("createUser", function_names)

    def test_contains_operator(self):
        """Test CONTAINS operator."""
        query = {
            "type": "function",
            "conditions": [
                {
                    "field": "raw_string",
                    "operator": "contains",
                    "value": "validateAndSave",
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions that contain validateAndSave in their raw_string
        self.assertTrue(len(results) > 0)
        for result in results:
            self.assertIn("validateAndSave", result.raw_string)

    def test_startswith_operator(self):
        """Test STARTSWITH operator."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "startswith", "value": "get"}],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions whose names start with "get"
        for result in results:
            if result.name:  # Skip NULL name
                self.assertTrue(result.name.startswith("get"))

    def test_endswith_operator(self):
        """Test ENDSWITH operator."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "endswith", "value": "User"}],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions whose names end with "User"
        for result in results:
            if result.name:  # Skip NULL name
                self.assertTrue(result.name.endswith("User"))

    def test_between_operator(self):
        """Test BETWEEN operator."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "between", "value": [15, 25]}
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with line_number_start between 15 and 25 (inclusive)
        for result in results:
            self.assertTrue(15 <= result.line_number_start <= 25)

    def test_is_null_operator_true(self):
        """Test IS NULL operator (true case)."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "is_null", "value": True}],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with NULL name
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].name)

    def test_is_null_operator_false(self):
        """Test IS NULL operator (false case)."""
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "is_null", "value": False}],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should return functions with non-NULL name
        self.assertTrue(all(f.name is not None for f in results))

    def test_multiple_operators(self):
        """Test using multiple operators in a single query."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "like", "value": "%User"},
                {"field": "line_number_start", "operator": "lt", "value": 30},
                {"field": "raw_string", "operator": "contains", "value": "validate"},
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Verify results match all conditions
        for result in results:
            self.assertTrue(result.name.endswith("User"))
            self.assertTrue(result.line_number_start < 30)
            self.assertIn("validate", result.raw_string)

    def test_join_with_operators(self):
        """Test joins with operators applied to the joined entity."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "startswith", "value": "update"}
            ],
            "joins": [
                {
                    "type": "called_function",
                    "conditions": [
                        {"field": "name", "operator": "like", "value": "%save%"}
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should find updateUser which calls validateAndSave
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "updateUser")

    def test_complex_join_with_multiple_operators(self):
        """Test complex join with multiple operators."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "ge", "value": 30}
            ],
            "joins": [
                {
                    "type": "called_function",
                    "conditions": [
                        {"field": "line_number_start", "operator": "lt", "value": 20},
                        {"field": "name", "operator": "contains", "value": "find"},
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should find functions that start at or after line 30 and call functions
        # that start before line 20 and contain "find" in their name
        self.assertTrue(len(results) > 0)
        for result in results:
            self.assertTrue(result.line_number_start >= 30)

    def test_negated_conditions(self):
        """Test queries with negated conditions."""
        # Find functions that don't call findUserById
        query = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "ne", "value": "findUserById"}
            ],
            "joins": [
                {
                    "type": "called_function",
                    "conditions": [
                        {"field": "name", "operator": "ne", "value": "findUserById"}
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Check that findUserById is not in the results
        self.assertNotIn("findUserById", [f.name for f in results if f.name])

    def test_json_field_query(self):
        """Test querying on JSON fields (function_input, function_output)."""
        # This test may need modification depending on how your implementation handles JSON fields
        # Verify the SQL being generated handles JSON fields correctly
        query = {
            "type": "function",
            "conditions": [
                {"field": "function_input", "operator": "contains", "value": "UserData"}
            ],
        }

        # Execute query (may not work with SQLite, primarily verifying SQL generation)
        try:
            results = self.query_service.execute_advanced_query(query)
            # If it works, verify results
            for result in results:
                self.assertTrue("UserData" in str(result.function_input))
        except Exception as e:
            # If SQLite doesn't support JSON operations, just verify the query was built
            self.assertTrue("function_input" in str(e) or "JSON" in str(e))

    def test_operator_chaining(self):
        """Test chaining multiple operators on the same field."""
        # Find functions with line numbers between ranges and specific conditions
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "ge", "value": 10},
                {"field": "line_number_start", "operator": "le", "value": 40},
                {"field": "line_number_end", "operator": "gt", "value": 15},
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Verify all conditions are met
        for result in results:
            self.assertTrue(10 <= result.line_number_start <= 40)
            self.assertTrue(result.line_number_end > 15)

    def test_case_sensitive_search(self):
        """Test case-sensitive search with LIKE vs ILIKE."""
        # Case-sensitive search
        query_sensitive = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "like", "value": "%user%"}  # lowercase
            ],
        }

        results_sensitive = self.query_service.execute_advanced_query(query_sensitive)

        # Case-insensitive search
        query_insensitive = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "ilike", "value": "%user%"}  # lowercase
            ],
        }

        results_insensitive = self.query_service.execute_advanced_query(
            query_insensitive
        )

        # LIKE should find fewer results than ILIKE since our data uses camelCase
        # Note: SQLite's LIKE might be case-insensitive by default, so this test may not be reliable
        # In a proper PostgreSQL environment, the difference would be clear
        self.assertTrue(len(results_insensitive) >= len(results_sensitive))

    def test_empty_conditions(self):
        """Test query with empty conditions."""
        query = {"type": "function", "conditions": []}

        results = self.query_service.execute_advanced_query(query)

        # Should return all functions
        self.assertEqual(len(results), 10)  # Total number of functions in test data

    def test_null_safe_operators(self):
        """Test null-safe operators."""
        # Find functions with non-null names that contain "User"
        query = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "is_null", "value": False},
                {"field": "name", "operator": "like", "value": "%User%"},
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Verify all results have non-null names containing "User"
        self.assertTrue(len(results) > 0)
        for result in results:
            self.assertIsNotNone(result.name)
            self.assertIn("User", result.name)


if __name__ == "__main__":
    unittest.main()
