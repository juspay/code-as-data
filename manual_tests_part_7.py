import unittest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from code_as_data.services.query_service import QueryService
from code_as_data.db.models import Base, Module, Trait, ImplBlock, Constant, TraitMethodSignature, Function, Type, Instance, Class, Import, FunctionCalled

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
        (1048, 'storage_impl::payouts::payout_attempt', 'crates/storage_impl/src/payouts/payout_attempt.rs'),
        (100, 'App.Services', 'app/services.py'),
        (101, 'App.models', 'app/models.py')
    ]
    for id, name, path in modules_data:
        session.add(Module(id=id, name=name, path=path))

    # Functions
    functions_data = [
        (1, 'to_storage_model', 'crates/storage_impl/src/payouts/payout_attempt.rs', 'storage_impl::payouts::payout_attempt', 997, 1, '[]', '[]', 1, 10, 'fn to_storage_model...'),
        (2, 'from_storage_model', 'crates/storage_impl/src/payouts/payout_attempt.rs', 'storage_impl::payouts::payout_attempt', 997, 1, '[{"type_name": "String"}]', '[]', 11, 20, 'fn from_storage_model...'),
        (3, 'fmt', 'crates/storage_impl/src/redis/kv_store.rs', 'storage_impl::redis::kv_store', 359, None, '[]', '[{"type_name": "i32"}]', 1, 10, 'fn fmt...'),
        (4, 'from', 'crates/storage_impl/src/redis/cache.rs', 'storage_impl::redis::cache', 1202, None, '[]', '[]', 1, 10, 'fn from...'),
        (5, 'is_db_not_found', 'crates/storage_impl/src/errors.rs', 'storage_impl::errors', 221, None, '[]', '[]', 1, 10, 'fn is_db_not_found...'),
        (6, 'process_item', 'app/services.py', 'App.Services', 100, None, '[]', '[]', 1, 10, 'for item in items:\n  process(item)'),
        (7, 'process_item_again', 'app/services.py', 'App.Services', 100, None, '[]', '[]', 11, 20, 'for item in items:\n  process(item)')
    ]
    for id, name, src_loc, module_name, module_id, impl_block_id, input_types, output_types, start, end, raw_string in functions_data:
        session.add(Function(id=id, name=name, src_loc=src_loc, module_name=module_name, module_id=module_id, impl_block_id=impl_block_id, input_types=input_types, output_types=output_types, line_number_start=start, line_number_end=end, raw_string=raw_string))

    # Types
    types_data = [
        (1, 'StorageModel', 'type StorageModel = ...', 'crates/storage_impl/src/callback_mapper.rs', 'data', 7, 7, 1327),
        (2, 'StorageResult', 'type StorageResult = ...', 'crates/storage_impl/src/errors.rs', 'type_alias', 5, 5, 221),
        (3, 'User', 'class User...', 'app/models.py', 'struct', 1, 10, 101)
    ]
    for id, type_name, raw_code, src_loc, type_of_type, line_number_start, line_number_end, module_id in types_data:
        session.add(Type(id=id, type_name=type_name, raw_code=raw_code, src_loc=src_loc, type_of_type=type_of_type, line_number_start=line_number_start, line_number_end=line_number_end, module_id=module_id))

    # Classes
    classes_data = [
        (1, 'User', 'class User...', 'app/models.py', 1, 10, 101)
    ]
    for id, name, definition, src_loc, start, end, module_id in classes_data:
        session.add(Class(id=id, class_name=name, class_definition=definition, src_location=src_loc, line_number_start=start, line_number_end=end, module_id=module_id))

    # Imports
    imports_data = [
        (1, 'storage_impl', None, 'crates/storage_impl/src/metrics.rs', False, None, None, None, None, False, None, 1, 1, 1327),
        (2, 'App.models', None, 'app/services.py', False, None, None, None, None, False, '["User"]', 1, 1, 100)
    ]
    for id, mod_name, pkg_name, src_loc, boot, safe, implicit, as_name, qual, hiding, specs, start, end, mod_id in imports_data:
        session.add(Import(id=id, module_name=mod_name, package_name=pkg_name, src_loc=src_loc, is_boot_source=boot, is_safe=safe, is_implicit=implicit, as_module_name=as_name, qualified_style=qual, is_hiding=hiding, hiding_specs=specs, line_number_start=start, line_number_end=end, module_id=mod_id))

    # FunctionCalled
    function_called_data = [
        (1, 1, 'User', 'App.models', 'TyConApp')
    ]
    for id, func_id, name, mod_name, type in function_called_data:
        session.add(FunctionCalled(id=id, function_id=func_id, name=name, module_name=mod_name, _type=type))

    session.commit()

class TestManualQueriesPart7(unittest.TestCase):
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

    def test_qs_009_execute_custom_query(self):
        print("\\n--- Testing QS-009: execute_custom_query ---")
        query_str = "SELECT * FROM function WHERE name = :name"
        params = {'name': 'from_storage_model'}
        results = self.query_service.execute_custom_query(query_str, params)
        print(f"Found {len(results)} functions with custom query.")
        self.assertEqual(len(results), 1)

    def test_qs_011_find_code_patterns(self):
        print("\\n--- Testing QS-011: find_code_patterns ---")
        results = self.query_service.find_code_patterns('for item in items:\n  process(item)', min_matches=2)
        print(f"Found {len(results)} functions with the specified code pattern.")
        self.assertEqual(len(results), 2)

    def test_qs_024_find_function_by_src_loc(self):
        print("\\n--- Testing QS-024: find_function_by_src_loc ---")
        result = self.query_service.find_function_by_src_loc('', 'crates/storage_impl/src/payouts/payout_attempt.rs', 5)
        print(f"Found function: {result.name if result else 'None'}")
        self.assertIsNotNone(result)

    def test_qs_026_find_class_by_module_name(self):
        print("\\n--- Testing QS-026: find_class_by_module_name ---")
        results = self.query_service.find_class_by_module_name('User', 'App.models')
        print(f"Found {len(results)} classes.")
        self.assertEqual(len(results), 1)

    def test_qs_027_find_type_by_src_loc(self):
        print("\\n--- Testing QS-027: find_type_by_src_loc ---")
        result = self.query_service.find_type_by_src_loc('', 'crates/storage_impl/src/errors.rs', 5)
        print(f"Found type: {result.type_name if result else 'None'}")
        self.assertIsNotNone(result)

    def test_qs_028_find_import_by_src_loc(self):
        print("\\n--- Testing QS-028: find_import_by_src_loc ---")
        result = self.query_service.find_import_by_src_loc('', 'crates/storage_impl/src/metrics.rs', 1)
        print(f"Found import: {result.module_name if result else 'None'}")
        self.assertIsNotNone(result)

    def test_qs_029_find_class_by_src_loc(self):
        print("\\n--- Testing QS-029: find_class_by_src_loc ---")
        result = self.query_service.find_class_by_src_loc('', 'app/models.py', 5)
        print(f"Found class: {result.class_name if result else 'None'}")
        self.assertIsNotNone(result)

    def test_qs_030_get_types_and_functions(self):
        print("\\n--- Testing QS-030: get_types_and_functions ---")
        results = self.query_service.get_types_and_functions(1)
        print(f"Found {len(results.get('local_types', []))} local types and {len(results.get('non_local_types', []))} non-local types.")
        self.assertGreater(len(results.get('local_types', [])), 0)

    def test_qs_033_get_types_used_in_function_prompt(self):
        print("\\n--- Testing QS-033: get_types_used_in_function_prompt ---")
        local_prompt, non_local_prompt = self.query_service.get_types_used_in_function_prompt(1)
        print(f"Local types prompt: {local_prompt}")
        print(f"Non-local types prompt: {non_local_prompt}")
        self.assertIsNotNone(non_local_prompt)

    def test_qs_034_generate_imports_for_element(self):
        print("\\n--- Testing QS-034: generate_imports_for_element ---")
        results = self.query_service.generate_imports_for_element('User', 'App.Services')
        print(f"Generated imports: {results}")
        self.assertIn('import App.models', results[0])

if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
