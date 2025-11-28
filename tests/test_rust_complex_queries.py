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
    TraitMethodSignature as DBTraitMethodSignature,
    function_dependency,
)
from code_as_data.db.connection import Base

class TestRustComplexQueries(unittest.TestCase):
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
        self.session.query(DBTraitMethodSignature).delete()
        self.session.query(DBModule).delete()
        self.session.commit()
        self.session.close()

    def _create_test_data(self):
        module1 = DBModule(name="my_crate::my_module", path="src/my_module.rs")
        module2 = DBModule(name="my_crate::utils", path="src/utils.rs")
        self.session.add_all([module1, module2])
        self.session.flush()

        trait1 = DBTrait(name="MyTrait", fully_qualified_path="my_crate::my_module::MyTrait", src_location="src/my_module.rs", module_id=module1.id)
        self.session.add(trait1)
        self.session.flush()

        impl_block1 = DBImplBlock(struct_name="MyStruct", trait_name="MyTrait", module_id=module1.id, trait_id=trait1.id)
        self.session.add(impl_block1)
        self.session.flush()

        function1 = DBFunction(name="my_method", module_id=module1.id, impl_block_id=impl_block1.id)
        function2 = DBFunction(name="another_method", module_id=module1.id, impl_block_id=impl_block1.id)
        function3 = DBFunction(name="util_func", module_id=module2.id)
        self.session.add_all([function1, function2, function3])
        self.session.flush()

        self.session.execute(
            function_dependency.insert().values(
                caller_id=function1.id, callee_id=function3.id
            )
        )

        trait_sig1 = DBTraitMethodSignature(name="my_trait_method", trait_id=trait1.id, module_id=module1.id)
        self.session.add(trait_sig1)

        constant1 = DBConstant(name="MY_CONST", fully_qualified_path="my_crate::my_module::MY_CONST", module_id=module1.id)
        self.session.add(constant1)
        self.session.commit()

    def test_simple_trait_query(self):
        query = {
            "type": "trait",
            "conditions": [{"field": "name", "operator": "eq", "value": "MyTrait"}],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "MyTrait")

    def test_impl_block_query(self):
        query = {
            "type": "impl_block",
            "conditions": [{"field": "struct_name", "operator": "eq", "value": "MyStruct"}],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].struct_name, "MyStruct")

    def test_trait_to_impl_block_join(self):
        query = {
            "type": "trait",
            "conditions": [{"field": "name", "operator": "eq", "value": "MyTrait"}],
            "joins": [
                {
                    "type": "impl_block",
                    "conditions": [],
                }
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].impl_blocks), 1)
        self.assertEqual(results[0].impl_blocks[0].struct_name, "MyStruct")

    def test_impl_block_to_function_join(self):
        query = {
            "type": "impl_block",
            "conditions": [{"field": "struct_name", "operator": "eq", "value": "MyStruct"}],
            "joins": [
                {
                    "type": "function",
                    "conditions": [],
                }
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].methods), 2)
        function_names = sorted([f.name for f in results[0].methods])
        self.assertEqual(function_names, ["another_method", "my_method"])

    def test_cross_module_rust_call(self):
        query = {
            "type": "function",
            "conditions": [{"field": "name", "operator": "eq", "value": "my_method"}],
            "joins": [
                {
                    "type": "called_function",
                    "conditions": [{"field": "name", "operator": "eq", "value": "util_func"}],
                }
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "my_method")

    def test_constant_query(self):
        query = {
            "type": "constant",
            "conditions": [{"field": "name", "operator": "eq", "value": "MY_CONST"}],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "MY_CONST")

    def test_trait_to_method_signature_join(self):
        query = {
            "type": "trait",
            "conditions": [{"field": "name", "operator": "eq", "value": "MyTrait"}],
            "joins": [
                {
                    "type": "trait_method_signature",
                    "conditions": [],
                }
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].methods), 1)
        self.assertEqual(results[0].methods[0].name, "my_trait_method")

    def test_cross_module_dependencies(self):
        """Test finding cross-module dependencies."""
        dependencies = self.query_service.find_cross_module_dependencies()

        self.assertTrue(len(dependencies) >= 1)

        dep_map = {}
        for dep in dependencies:
            caller = dep["caller_module"]["name"]
            callee = dep["callee_module"]["name"]
            key = f"{caller}->{callee}"
            dep_map[key] = dep["call_count"]

        self.assertIn("my_crate::my_module->my_crate::utils", dep_map)

    def test_find_by_fully_qualified_path(self):
        results = self.query_service.find_by_fully_qualified_path("my_crate::my_module::MyTrait")
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], DBTrait)

    def test_find_by_visibility(self):
        # Add visibility to a function for testing
        function = self.session.query(DBFunction).filter_by(name="my_method").one()
        function.visibility = "public"
        self.session.commit()

        results = self.query_service.find_by_visibility("function", "public")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "my_method")

    def test_find_by_crate(self):
        # Add crate_name to a constant for testing
        constant = self.session.query(DBConstant).filter_by(name="MY_CONST").one()
        constant.crate_name = "my_crate"
        self.session.commit()

        results = self.query_service.find_by_crate("constant", "my_crate")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "MY_CONST")

    def test_find_functions_with_input_type(self):
        # Add input_types to a function for testing
        function = self.session.query(DBFunction).filter_by(name="my_method").one()
        function.input_types = [{"type_name": "String"}]
        self.session.commit()

        results = self.query_service.find_functions_with_input_type("String")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "my_method")

    def test_find_functions_with_output_type(self):
        # Add output_types to a function for testing
        function = self.session.query(DBFunction).filter_by(name="my_method").one()
        function.output_types = [{"type_name": "i32"}]
        self.session.commit()

        results = self.query_service.find_functions_with_output_type("i32")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "my_method")

    def test_find_entities_with_attribute(self):
        # Add attributes to a function for testing
        function = self.session.query(DBFunction).filter_by(name="my_method").one()
        function.attributes = ["#[derive(Debug)]"]
        self.session.commit()

        results = self.query_service.find_entities_with_attribute("function", "#[derive(Debug)]")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "my_method")


if __name__ == "__main__":
    unittest.main()
