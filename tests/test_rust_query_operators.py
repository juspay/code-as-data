import unittest
import sys
import os
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from code_as_data.services.query_service import QueryService
from code_as_data.db.models import (
    Module as DBModule,
    Function as DBFunction,
    Trait as DBTrait,
    ImplBlock as DBImplBlock,
    Constant as DBConstant,
    function_dependency,
)
from code_as_data.db.connection import Base

class TestRustQueryOperators(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        cls.Session = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(cls.engine)

    def setUp(self):
        self.session = self.Session()
        self.query_service = QueryService(self.session)
        self._create_test_data()

    def tearDown(self):
        self.session.query(function_dependency).delete()
        self.session.query(DBFunction).delete()
        self.session.query(DBImplBlock).delete()
        self.session.query(DBTrait).delete()
        self.session.query(DBConstant).delete()
        self.session.query(DBModule).delete()
        self.session.commit()
        self.session.close()

    def _create_test_data(self):
        module1 = DBModule(name="my_crate::my_module", path="src/my_module.rs")
        self.session.add(module1)
        self.session.flush()

        trait1 = DBTrait(name="MyTrait", fully_qualified_path="my_crate::my_module::MyTrait", src_location="src/my_module.rs", module_id=module1.id)
        self.session.add(trait1)
        self.session.flush()

        constant1 = DBConstant(name="MY_CONST", fully_qualified_path="my_crate::my_module::MY_CONST", module_id=module1.id)
        self.session.add(constant1)

        function1 = DBFunction(name="my_method", module_id=module1.id, line_number_start=10)
        function2 = DBFunction(name="another_method", module_id=module1.id, line_number_start=20)
        function3 = DBFunction(name="util_func", module_id=module1.id, line_number_start=30)
        function4 = DBFunction(name=None, module_id=module1.id, line_number_start=40)
        self.session.add_all([function1, function2, function3, function4])

        self.session.commit()

    def test_like_operator_on_rust_trait(self):
        query = {
            "type": "trait",
            "conditions": [{"field": "name", "operator": "like", "value": "%Trait%"}],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "MyTrait")

    def test_in_operator_on_rust_constant(self):
        query = {
            "type": "constant",
            "conditions": [
                {
                    "field": "fully_qualified_path",
                    "operator": "in",
                    "value": [
                        "my_crate::my_module::MY_CONST",
                        "my_crate::my_module::OTHER_CONST",
                    ],
                }
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "MY_CONST")

    def test_between_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "between", "value": [1, 100]}
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 4)

    def test_startswith_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "startswith", "value": "my"}
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "my_method")

    def test_endswith_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [
                {"field": "name", "operator": "endswith", "value": "method"}
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 2)

    def test_eq_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "eq", "value": "my_method"}],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "my_method")

    def test_ne_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "ne", "value": "my_method"}],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 2)

    def test_gt_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "gt", "value": 20}
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 2)

    def test_lt_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "lt", "value": 20}
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)

    def test_ge_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "ge", "value": 30}
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 2)

    def test_le_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [
                {"field": "line_number_start", "operator": "le", "value": 10}
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)

    def test_ilike_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "ilike", "value": "%METHOD%"}],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 2)

    def test_not_in_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [
                {
                    "field": "name",
                    "operator": "not_in",
                    "value": ["my_method", "another_method"],
                }
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)

    def test_is_null_operator_on_rust_function(self):
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "is_null", "value": True}],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
