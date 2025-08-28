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

class TestRustPatternMatching(unittest.TestCase):
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

        constant1 = DBConstant(name="MY_CONST", fully_qualified_path="my_crate::my_module::MY_CONST", module_id=module1.id)
        self.session.add(constant1)
        self.session.commit()

    def test_pattern_match_rust_function_call(self):
        pattern = {
            "type": "function_call",
            "caller": "my_method",
            "callee": "util_func",
            "mode": "calls",
        }
        matches = self.query_service.pattern_match(pattern)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["caller"]["name"], "my_method")
        self.assertEqual(matches[0]["callee"]["name"], "util_func")

    def test_pattern_match_struct_impl_trait(self):
        pattern = {
            "type": "struct_impl_trait",
            "struct_name": "MyStruct",
            "trait_name": "MyTrait",
        }
        matches = self.query_service.pattern_match(pattern)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["struct"]["name"], "MyStruct")
        self.assertEqual(matches[0]["trait"]["name"], "MyTrait")

    def test_pattern_match_function_calls_method_on_trait_impl(self):
        pattern = {
            "type": "function_calls_method_on_trait_impl",
            "caller_name": "my_method",
            "trait_name": "MyTrait",
        }
        matches = self.query_service.pattern_match(pattern)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["function"]["name"], "my_method")
        self.assertEqual(matches[0]["struct"]["name"], "MyStruct")
        self.assertEqual(matches[0]["trait"]["name"], "MyTrait")

    def test_cross_module_call_pattern(self):
        query = {
            "type": "module",
            "conditions": [
                {"field": "name", "operator": "eq", "value": "my_crate::my_module"}
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
                                    "value": 2,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        results = self.query_service.execute_advanced_query(query)
        self.assertEqual(len(results), 2)

    def test_code_structure_pattern(self):
        pattern = {"type": "code_structure", "structure_type": "nested_function"}
        matches = self.query_service.pattern_match(pattern)
        self.assertEqual(len(matches), 0)


if __name__ == "__main__":
    unittest.main()
