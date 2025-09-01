import unittest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from code_as_data.services.query_service import QueryService
from code_as_data.db.models import Base, Module, Trait, ImplBlock, Constant, TraitMethodSignature, Function, Type, Instance, Class, Import

def populate_test_data(session):
    # Modules
    modules_data = [
        (1, 'connectors::aci', 'connectors::aci'),
        (2, 'router::tests::connectors::redsys', 'crates/router/tests/connectors/redsys'),
        (3, 'common_utils::types::user::theme', 'crates/common_utils/src/types/user/theme'),
        (4, 'router::db::role', 'crates/router/src/db/role'),
        (5, 'connectors::netcetera', 'connectors::netcetera'),
        (997, 'storage_impl::payouts::payout_attempt', 'crates/storage_impl/src/payouts/payout_attempt.rs'),
        (359, 'storage_impl::redis::kv_store', 'crates/storage_impl/src/redis/kv_store.rs'),
        (1202, 'storage_impl::redis::cache', 'crates/storage_impl/src/redis/cache.rs'),
        (221, 'storage_impl::errors', 'crates/storage_impl/src/errors.rs'),
        (1327, 'storage_impl', 'crates/storage_impl/src/metrics.rs'),
        (808, 'unknown::unknown', 'crates/storage_impl/src/callback_mapper.rs'),
        (1048, 'storage_impl::payouts::payout_attempt', 'crates/storage_impl/src/payouts/payout_attempt.rs')
    ]
    for id, name, path in modules_data:
        session.add(Module(id=id, name=name, path=path))

    # Functions
    functions_data = [
        (1, 'to_storage_model', 'crates/storage_impl/src/payouts/payout_attempt.rs', 'storage_impl::payouts::payout_attempt', 997, 1, '[]', '[]'),
        (2, 'from_storage_model', 'crates/storage_impl/src/payouts/payout_attempt.rs', 'storage_impl::payouts::payout_attempt', 997, 1, '[{"type_name": "String"}]', '[]'),
        (3, 'fmt', 'crates/storage_impl/src/redis/kv_store.rs', 'storage_impl::redis::kv_store', 359, None, '[]', '[{"type_name": "i32"}]'),
        (4, 'from', 'crates/storage_impl/src/redis/cache.rs', 'storage_impl::redis::cache', 1202, None, '[]', '[]'),
        (5, 'is_db_not_found', 'crates/storage_impl/src/errors.rs', 'storage_impl::errors', 221, None, '[]', '[]')
    ]
    for id, name, src_loc, module_name, module_id, impl_block_id, input_types, output_types in functions_data:
        session.add(Function(id=id, name=name, src_loc=src_loc, module_name=module_name, module_id=module_id, impl_block_id=impl_block_id, input_types=input_types, output_types=output_types))

    # Types
    types_data = [
        (1, 'StorageModel', 'crates/storage_impl/src/callback_mapper.rs', 'data', 7, 7, 1327),
        (2, 'StorageResult', 'crates/storage_impl/src/errors.rs', 'type_alias', 5, 5, 221)
    ]
    for id, type_name, raw_code, type_of_type, line_number_start, line_number_end, module_id in types_data:
        session.add(Type(id=id, type_name=type_name, raw_code=raw_code, type_of_type=type_of_type, line_number_start=line_number_start, line_number_end=line_number_end, module_id=module_id))

    # Trait Method Signatures
    trait_method_signatures_data = [
        (1, 'to_redis_failed_response', 'storage_impl::to_redis_failed_response', '[{"type_name": "Self", "crate_name": "", "module_path": "", "generic_args": [], "is_generic_param": true, "src_location": "crates/storage_impl/src/errors.rs"}, {"type_name": "&str", "crate_name": "core", "module_path": "primitive", "generic_args": [], "is_generic_param": false, "src_location": "crates/storage_impl/src/errors.rs"}]', '[{"type_name": "Report<StorageError>", "crate_name": "error_stack", "module_path": "report", "generic_args": [{"type_name": "StorageError", "crate_name": "storage_impl", "module_path": "errors", "generic_args": [], "is_generic_param": false, "src_location": "crates/storage_impl/src/errors.rs"}], "is_generic_param": false, "src_location": "crates/storage_impl/src/errors.rs"}]', 'crates/storage_impl/src/errors.rs', 'fn to_redis_failed_response(self, key: &str) -> error_stack::Report<StorageError>;', 96, 96, 'storage_impl', 'pub', '[]', False, False, None)
    ]
    for id, name, fqp, inputs, outputs, src_loc, src_code, start, end, mod_name, visibility, attrs, is_async, is_unsafe, trait_id in trait_method_signatures_data:
        session.add(TraitMethodSignature(id=id, name=name, fully_qualified_path=fqp, input_types=inputs, output_types=outputs, src_location=src_loc, src_code=src_code, line_number_start=start, line_number_end=end, module_name=mod_name, visibility=visibility, attributes=attrs, is_async=is_async, is_unsafe=is_unsafe, trait_id=trait_id))

    session.commit()

class TestManualQueriesPart5(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        cls.Session = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(cls.engine)

    def setUp(self):
        self.connection = self.engine.connect()
        self.trans = self.connection.begin()
        self.session = self.Session(bind=self.connection)
        populate_test_data(self.session)
        self.query_service = QueryService(self.session)

    def tearDown(self):
        self.session.close()
        self.trans.rollback()
        self.connection.close()

    def test_qs_001_get_all_modules(self):
        print("\\n--- Testing QS-001: get_all_modules ---")
        results = self.query_service.get_all_modules()
        print(f"Found {len(results)} modules.")
        self.assertGreater(len(results), 0)

    def test_qs_002_get_module_by_name(self):
        print("\\n--- Testing QS-002: get_module_by_name ---")
        result = self.query_service.get_module_by_name('connectors::aci')
        print(f"Found module: {result.__dict__ if result else 'None'}")
        self.assertIsNotNone(result)

    def test_qs_003_get_functions_by_module(self):
        print("\\n--- Testing QS-003: get_functions_by_module ---")
        results = self.query_service.get_functions_by_module(997)
        print(f"Found {len(results)} functions for module 997.")
        self.assertEqual(len(results), 2)

    def test_qs_004_get_function_by_name(self):
        print("\\n--- Testing QS-004: get_function_by_name ---")
        results = self.query_service.get_function_by_name('from_storage_model', 997)
        print(f"Found {len(results)} functions with name 'from_storage_model' in module 997.")
        self.assertEqual(len(results), 1)

    def test_qs_023_find_type_by_module_name(self):
        print("\\n--- Testing QS-023: find_type_by_module_name ---")
        results = self.query_service.find_type_by_module_name('StorageResult', 'storage_impl::errors')
        print(f"Found {len(results)} types with name 'StorageResult' in module 'storage_impl::errors'.")
        self.assertEqual(len(results), 1)

    def test_qs_049_get_all_trait_method_signatures(self):
        print("\\n--- Testing QS-049: get_all_trait_method_signatures ---")
        results = self.query_service.get_all_trait_method_signatures()
        print(f"Found {len(results)} trait method signatures.")
        self.assertGreater(len(results), 0)

    def test_qs_054_find_functions_with_input_type(self):
        print("\\n--- Testing QS-054: find_functions_with_input_type ---")
        results = self.query_service.find_functions_with_input_type('String')
        print(f"Found {len(results)} functions with input type 'String'.")
        self.assertEqual(len(results), 1)

    def test_qs_055_find_functions_with_output_type(self):
        print("\\n--- Testing QS-055: find_functions_with_output_type ---")
        results = self.query_service.find_functions_with_output_type('i32')
        print(f"Found {len(results)} functions with output type 'i32'.")
        self.assertEqual(len(results), 1)

if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
