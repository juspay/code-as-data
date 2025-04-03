import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Adjust path to import from src directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from code_as_data.services.query_service import QueryService
from code_as_data.db.models import (
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
    type_dependency,
)
from code_as_data.db.connection import Base


class TestPatternMatching(unittest.TestCase):
    """Test cases for the pattern matching capabilities.

    These tests verify that the pattern matching system can correctly identify
    various code patterns and relationships in the test codebase.
    """

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
        """Create test data for pattern matching tests.

        This creates a simulated MVC application structure with:
        - Controllers that interact with Models and Views
        - Models that retrieve and validate data
        - Views that render data
        - Utility functions used across the application
        """
        # Create modules
        module1 = Module(id=1, name="app.controllers", path="app/controllers")
        module2 = Module(id=2, name="app.models", path="app/models")
        module3 = Module(id=3, name="app.views", path="app/views")
        module4 = Module(id=4, name="app.utils", path="app/utils")

        self.session.add_all([module1, module2, module3, module4])
        self.session.flush()

        # Create functions - Controllers
        controller_functions = [
            Function(
                id=1,
                name="UserController",
                function_signature="Request -> Response",
                raw_string="""UserController req = do
                    user <- getUserModel req.id
                    if isValid user
                        then renderUserView user
                        else renderErrorView "Invalid user"
                """,
                src_loc="app/controllers/user_controller.hs:10",
                line_number_start=10,
                line_number_end=20,
                type_enum="function",
                module_id=1,
            ),
            Function(
                id=2,
                name="ProductController",
                function_signature="Request -> Response",
                raw_string="""ProductController req = do
                    product <- getProductModel req.id
                    if isValid product
                        then renderProductView product
                        else renderErrorView "Invalid product"
                """,
                src_loc="app/controllers/product_controller.hs:10",
                line_number_start=10,
                line_number_end=20,
                type_enum="function",
                module_id=1,
            ),
            Function(
                id=3,
                name="AdminController",
                function_signature="Request -> Response",
                raw_string="""AdminController req = do
                    if isAdmin req.user
                        then do
                            users <- getAllUsers
                            renderAdminView users
                        else renderErrorView "Access denied"
                """,
                src_loc="app/controllers/admin_controller.hs:10",
                line_number_start=10,
                line_number_end=20,
                type_enum="function",
                module_id=1,
            ),
        ]

        # Create functions - Models
        model_functions = [
            Function(
                id=4,
                name="getUserModel",
                function_signature="ID -> User",
                raw_string="""getUserModel id = do
                    user <- queryDatabase "SELECT * FROM users WHERE id = ?" [id]
                    validateUser user
                """,
                src_loc="app/models/user_model.hs:5",
                line_number_start=5,
                line_number_end=10,
                type_enum="function",
                module_id=2,
            ),
            Function(
                id=5,
                name="getProductModel",
                function_signature="ID -> Product",
                raw_string="""getProductModel id = do
                    product <- queryDatabase "SELECT * FROM products WHERE id = ?" [id]
                    validateProduct product
                """,
                src_loc="app/models/product_model.hs:5",
                line_number_start=5,
                line_number_end=10,
                type_enum="function",
                module_id=2,
            ),
            Function(
                id=6,
                name="getAllUsers",
                function_signature="[User]",
                raw_string="""getAllUsers = do
                    users <- queryDatabase "SELECT * FROM users" []
                    mapM validateUser users
                """,
                src_loc="app/models/user_model.hs:15",
                line_number_start=15,
                line_number_end=20,
                type_enum="function",
                module_id=2,
            ),
        ]

        # Create functions - Views
        view_functions = [
            Function(
                id=7,
                name="renderUserView",
                function_signature="User -> Response",
                raw_string="""renderUserView user = do
                    template <- loadTemplate "user_view.html"
                    renderTemplate template user
                """,
                src_loc="app/views/user_view.hs:5",
                line_number_start=5,
                line_number_end=10,
                type_enum="function",
                module_id=3,
            ),
            Function(
                id=8,
                name="renderProductView",
                function_signature="Product -> Response",
                raw_string="""renderProductView product = do
                    template <- loadTemplate "product_view.html"
                    renderTemplate template product
                """,
                src_loc="app/views/product_view.hs:5",
                line_number_start=5,
                line_number_end=10,
                type_enum="function",
                module_id=3,
            ),
            Function(
                id=9,
                name="renderAdminView",
                function_signature="[User] -> Response",
                raw_string="""renderAdminView users = do
                    template <- loadTemplate "admin_view.html"
                    renderTemplate template users
                """,
                src_loc="app/views/admin_view.hs:5",
                line_number_start=5,
                line_number_end=10,
                type_enum="function",
                module_id=3,
            ),
            Function(
                id=10,
                name="renderErrorView",
                function_signature="String -> Response",
                raw_string="""renderErrorView message = do
                    template <- loadTemplate "error_view.html"
                    renderTemplate template message
                """,
                src_loc="app/views/error_view.hs:5",
                line_number_start=5,
                line_number_end=10,
                type_enum="function",
                module_id=3,
            ),
        ]

        # Create functions - Utils
        util_functions = [
            Function(
                id=11,
                name="loadTemplate",
                function_signature="String -> Template",
                raw_string="""loadTemplate path = do
                    content <- readFile path
                    parseTemplate content
                """,
                src_loc="app/utils/template.hs:5",
                line_number_start=5,
                line_number_end=10,
                type_enum="function",
                module_id=4,
            ),
            Function(
                id=12,
                name="renderTemplate",
                function_signature="Template -> a -> Response",
                raw_string="""renderTemplate template data = do
                    html <- applyTemplate template data
                    return $ Response 200 html
                """,
                src_loc="app/utils/template.hs:15",
                line_number_start=15,
                line_number_end=20,
                type_enum="function",
                module_id=4,
            ),
            Function(
                id=13,
                name="isValid",
                function_signature="a -> Bool",
                raw_string="isValid x = x /= null",
                src_loc="app/utils/validation.hs:5",
                line_number_start=5,
                line_number_end=6,
                type_enum="function",
                module_id=4,
            ),
            Function(
                id=14,
                name="isAdmin",
                function_signature="User -> Bool",
                raw_string='isAdmin user = user.role == "admin"',
                src_loc="app/utils/auth.hs:10",
                line_number_start=10,
                line_number_end=12,
                type_enum="function",
                module_id=4,
            ),
            Function(
                id=15,
                name="validateUser",
                function_signature="User -> User",
                raw_string="""validateUser user = do
                    if isValid user.id && isValid user.name
                        then return user
                        else throw "Invalid user"
                """,
                src_loc="app/utils/validation.hs:10",
                line_number_start=10,
                line_number_end=15,
                type_enum="function",
                module_id=4,
            ),
            Function(
                id=16,
                name="validateProduct",
                function_signature="Product -> Product",
                raw_string="""validateProduct product = do
                    if isValid product.id && isValid product.name
                        then return product
                        else throw "Invalid product"
                """,
                src_loc="app/utils/validation.hs:20",
                line_number_start=20,
                line_number_end=25,
                type_enum="function",
                module_id=4,
            ),
        ]

        self.session.add_all(
            controller_functions + model_functions + view_functions + util_functions
        )
        self.session.flush()

        # Create where functions
        where_function1 = WhereFunction(
            id=1,
            name="handleError",
            function_signature="Error -> Response",
            raw_string="handleError e = Response 500 (show e)",
            src_loc="app/controllers/user_controller.hs:15",
            parent_function_id=1,
        )

        where_function2 = WhereFunction(
            id=2,
            name="handleError",
            function_signature="Error -> Response",
            raw_string="handleError e = Response 500 (show e)",
            src_loc="app/controllers/product_controller.hs:15",
            parent_function_id=2,
        )

        self.session.add_all([where_function1, where_function2])
        self.session.flush()

        # Create types
        type1 = Type(
            id=1,
            type_name="User",
            raw_code="data User = User { id :: ID, name :: String, email :: String, role :: String }",
            src_loc="app/models/types.hs:10",
            type_of_type="data",
            line_number_start=10,
            line_number_end=15,
            module_id=2,
        )

        type2 = Type(
            id=2,
            type_name="Product",
            raw_code="data Product = Product { id :: ID, name :: String, price :: Double }",
            src_loc="app/models/types.hs:20",
            type_of_type="data",
            line_number_start=20,
            line_number_end=25,
            module_id=2,
        )

        type3 = Type(
            id=3,
            type_name="Response",
            raw_code="data Response = Response { status :: Int, body :: String }",
            src_loc="app/utils/http.hs:5",
            type_of_type="data",
            line_number_start=5,
            line_number_end=10,
            module_id=4,
        )

        type4 = Type(
            id=4,
            type_name="Request",
            raw_code="data Request = Request { path :: String, method :: String, params :: Map String String, user :: Maybe User }",
            src_loc="app/utils/http.hs:15",
            type_of_type="data",
            line_number_start=15,
            line_number_end=20,
            module_id=4,
        )

        type5 = Type(
            id=5,
            type_name="Template",
            raw_code="data Template = Template { content :: String, vars :: Map String String }",
            src_loc="app/utils/template.hs:10",
            type_of_type="data",
            line_number_start=10,
            line_number_end=15,
            module_id=4,
        )

        self.session.add_all([type1, type2, type3, type4, type5])
        self.session.flush()

        # Set up function dependencies
        # Controllers -> Models
        self.session.execute(
            function_dependency.insert().values(caller_id=1, callee_id=4)
        )  # UserController calls getUserModel
        self.session.execute(
            function_dependency.insert().values(caller_id=2, callee_id=5)
        )  # ProductController calls getProductModel
        self.session.execute(
            function_dependency.insert().values(caller_id=3, callee_id=6)
        )  # AdminController calls getAllUsers

        # Controllers -> Views
        self.session.execute(
            function_dependency.insert().values(caller_id=1, callee_id=7)
        )  # UserController calls renderUserView
        self.session.execute(
            function_dependency.insert().values(caller_id=1, callee_id=10)
        )  # UserController calls renderErrorView
        self.session.execute(
            function_dependency.insert().values(caller_id=2, callee_id=8)
        )  # ProductController calls renderProductView
        self.session.execute(
            function_dependency.insert().values(caller_id=2, callee_id=10)
        )  # ProductController calls renderErrorView
        self.session.execute(
            function_dependency.insert().values(caller_id=3, callee_id=9)
        )  # AdminController calls renderAdminView
        self.session.execute(
            function_dependency.insert().values(caller_id=3, callee_id=10)
        )  # AdminController calls renderErrorView

        # Controllers -> Utils
        self.session.execute(
            function_dependency.insert().values(caller_id=1, callee_id=13)
        )  # UserController calls isValid
        self.session.execute(
            function_dependency.insert().values(caller_id=2, callee_id=13)
        )  # ProductController calls isValid
        self.session.execute(
            function_dependency.insert().values(caller_id=3, callee_id=14)
        )  # AdminController calls isAdmin

        # Models -> Utils
        self.session.execute(
            function_dependency.insert().values(caller_id=4, callee_id=15)
        )  # getUserModel calls validateUser
        self.session.execute(
            function_dependency.insert().values(caller_id=5, callee_id=16)
        )  # getProductModel calls validateProduct
        self.session.execute(
            function_dependency.insert().values(caller_id=6, callee_id=15)
        )  # getAllUsers calls validateUser

        # Views -> Utils
        self.session.execute(
            function_dependency.insert().values(caller_id=7, callee_id=11)
        )  # renderUserView calls loadTemplate
        self.session.execute(
            function_dependency.insert().values(caller_id=7, callee_id=12)
        )  # renderUserView calls renderTemplate
        self.session.execute(
            function_dependency.insert().values(caller_id=8, callee_id=11)
        )  # renderProductView calls loadTemplate
        self.session.execute(
            function_dependency.insert().values(caller_id=8, callee_id=12)
        )  # renderProductView calls renderTemplate
        self.session.execute(
            function_dependency.insert().values(caller_id=9, callee_id=11)
        )  # renderAdminView calls loadTemplate
        self.session.execute(
            function_dependency.insert().values(caller_id=9, callee_id=12)
        )  # renderAdminView calls renderTemplate
        self.session.execute(
            function_dependency.insert().values(caller_id=10, callee_id=11)
        )  # renderErrorView calls loadTemplate
        self.session.execute(
            function_dependency.insert().values(caller_id=10, callee_id=12)
        )  # renderErrorView calls renderTemplate

        # Utils -> Utils
        self.session.execute(
            function_dependency.insert().values(caller_id=15, callee_id=13)
        )  # validateUser calls isValid
        self.session.execute(
            function_dependency.insert().values(caller_id=16, callee_id=13)
        )  # validateProduct calls isValid

        # Type dependencies
        self._safely_add_dependency(
            type_dependency, dependent_id=1, dependency_id=4
        )  # User depends on Request
        self._safely_add_dependency(
            type_dependency, dependent_id=2, dependency_id=4
        )  # Product depends on Request
        self._safely_add_dependency(
            type_dependency, dependent_id=3, dependency_id=1
        )  # Response depends on User
        self._safely_add_dependency(
            type_dependency, dependent_id=3, dependency_id=2
        )  # Response depends on Product

    def _safely_add_dependency(self, table, **kwargs):
        """Safely add a dependency entry, ignoring duplicate errors."""
        try:
            self.session.execute(table.insert().values(**kwargs))
        except Exception as e:
            # Skip unique constraint errors
            if "UNIQUE constraint failed" not in str(e):
                raise
        # Commit all test data
        self.session.commit()

    def test_function_call_pattern(self):
        """Test identifying calls between different layers of the application."""
        # Test controllers calling models
        pattern = {
            "type": "function_call",
            "caller": "Controller",  # Functions with "Controller" in name
            "callee": "Model",  # That call functions with "Model" in name
            "mode": "calls",
        }

        matches = self.query_service.pattern_match(pattern)

        # Should find UserController->getUserModel, ProductController->getProductModel, etc.
        self.assertEqual(len(matches), 2)

        # Verify specific relationships
        found_relationships = set()
        for match in matches:
            caller = match["caller"]["name"]
            callee = match["callee"]["name"]
            found_relationships.add(f"{caller}->{callee}")

        expected_relationships = {
            "UserController->getUserModel",
            "ProductController->getProductModel",
        }

        self.assertEqual(found_relationships, expected_relationships)

    def test_called_by_pattern(self):
        """Test identifying functions called by specific other functions."""
        # Test which view functions are called by controllers
        pattern = {
            "type": "function_call",
            "caller": "Controller",
            "callee": "render",
            "mode": "calls",
        }

        matches = self.query_service.pattern_match(pattern)

        # Should find all renderXView functions called by controllers
        self.assertTrue(
            len(matches) >= 6
        )  # Each controller calls at least 2 render functions

        # Count occurrences of each view function
        view_counts = {}
        for match in matches:
            callee = match["callee"]["name"]
            view_counts[callee] = view_counts.get(callee, 0) + 1

        # Every controller calls renderErrorView as a fallback
        self.assertEqual(view_counts.get("renderErrorView", 0), 3)

    def test_type_usage_pattern(self):
        """Test identifying where specific types are used."""
        pattern = {"type": "type_usage", "type_name": "User", "usage_in": "function"}

        matches = self.query_service.pattern_match(pattern)

        # Should find functions that use the User type
        self.assertTrue(len(matches) > 0)

        # Verify at least some of the expected functions are found
        function_names = [match["function"]["name"] for match in matches]
        user_related_functions = ["getUserModel", "validateUser", "isAdmin"]

        for func_name in user_related_functions:
            self.assertTrue(
                any(func_name in f for f in function_names),
                f"Expected to find {func_name} in functions using User type",
            )

    def test_code_structure_pattern(self):
        """Test identifying specific code structures."""
        pattern = {"type": "code_structure", "structure_type": "nested_function"}

        matches = self.query_service.pattern_match(pattern)

        # Should find functions with where functions (nested functions)
        self.assertEqual(
            len(matches), 2
        )  # UserController and ProductController have handleError

        # Verify the specific parent functions
        parent_functions = set(match["parent_function"]["name"] for match in matches)
        self.assertEqual(parent_functions, {"UserController", "ProductController"})

    def test_cross_module_call_pattern(self):
        """Test identifying calls between modules."""
        query = {
            "type": "module",
            "conditions": [
                {"field": "name", "operator": "eq", "value": "app.controllers"}
            ],
            "joins": [
                {
                    "type": "function",
                    "conditions": [],
                    "joins": [
                        {
                            "type": "called_function",
                            "conditions": [
                                {
                                    "field": "module_id",
                                    "operator": "eq",
                                    "value": 3,
                                }  # app.views module
                            ],
                        }
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # Should find controller functions that call view functions
        self.assertTrue(len(results) > 0)

        # Alternative approach using pattern matching
        deps = self.query_service.find_cross_module_dependencies()

        # Convert to a testable format
        module_calls = {}
        for dep in deps:
            caller = dep["caller_module"]["name"]
            callee = dep["callee_module"]["name"]
            key = f"{caller}->{callee}"
            module_calls[key] = dep["call_count"]

        # Verify calls from controllers to views
        self.assertIn("app.controllers->app.views", module_calls)

    def test_find_similar_functions(self):
        """Test identifying similar functions based on code patterns."""
        # First find a reference function
        validate_func = (
            self.session.query(Function).filter(Function.name == "validateUser").first()
        )

        # Find similar functions
        similar_functions = self.query_service.find_similar_functions(
            validate_func.id, threshold=0.4
        )

        # validateProduct should be similar to validateUser
        similar_names = [func["function"]["name"] for func in similar_functions]
        self.assertIn("validateProduct", similar_names)

    def test_find_complex_queries(self):
        """Test complex query to find controller functions with specific patterns."""
        # Query to find controllers that validate input and handle errors
        query = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "like", "value": "%Controller%"},
                {"field": "raw_string", "operator": "contains", "value": "if isValid"},
            ],
            "joins": [
                {
                    "type": "called_function",
                    "conditions": [
                        {"field": "name", "operator": "like", "value": "render%View"}
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # UserController and ProductController should match
        self.assertEqual(len(results), 2)
        function_names = sorted([f.name for f in results])
        self.assertEqual(function_names, ["ProductController", "UserController"])

    def test_find_all_render_template_calls(self):
        """Test finding all views that use the same rendering function."""
        query = {
            "type": "function",
            "conditions": [
                {"field": "module_id", "operator": "eq", "value": 3}  # app.views module
            ],
            "joins": [
                {
                    "type": "called_function",
                    "conditions": [
                        {"field": "name", "operator": "eq", "value": "renderTemplate"}
                    ],
                }
            ],
        }

        results = self.query_service.execute_advanced_query(query)

        # All view functions should call renderTemplate
        self.assertEqual(len(results), 4)  # All 4 view functions

    def test_find_code_patterns(self):
        """Test finding specific code patterns across functions."""
        # Look for the error handling pattern
        pattern_code = """if isValid
                        then
                        else renderErrorView"""

        pattern_matches = self.query_service.find_code_patterns(
            pattern_code, min_matches=2  # Require at least 2 matching lines
        )

        # Should find this pattern in UserController and ProductController
        self.assertTrue(len(pattern_matches) >= 2)

        # Verify at least UserController and ProductController are found
        function_names = [match["function"]["name"] for match in pattern_matches]
        self.assertTrue(
            "UserController" in function_names or "ProductController" in function_names,
            "Expected to find controllers with the error handling pattern",
        )

    def test_module_coupling_analysis(self):
        """Test analyzing coupling between modules."""
        coupling_metrics = self.query_service.analyze_module_coupling()

        # Should provide metrics for all modules
        self.assertEqual(len(coupling_metrics["module_metrics"]), 4)

        # Controllers should have high outgoing dependencies
        controller_metrics = None
        for module in coupling_metrics["module_metrics"]:
            if module["name"] == "app.controllers":
                controller_metrics = module
                break

        self.assertIsNotNone(controller_metrics)
        self.assertTrue(controller_metrics["outgoing"] > 0)

        # Utils should have high incoming dependencies
        utils_metrics = None
        for module in coupling_metrics["module_metrics"]:
            if module["name"] == "app.utils":
                utils_metrics = module
                break

        self.assertIsNotNone(utils_metrics)
        self.assertTrue(utils_metrics["incoming"] > 0)


if __name__ == "__main__":
    unittest.main()
