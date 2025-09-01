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

    # Instances
    instances_data = [
        (1, 'instance_definition_1', 'instance_signature_1', 'src_loc_1', 1, 10, 1327),
        (2, 'instance_definition_2', 'instance_signature_2', 'src_loc_2', 11, 20, 1327)
    ]
    for id, definition, signature, src_loc, start, end, module_id in instances_data:
        session.add(Instance(id=id, instance_definition=definition, instance_signature=signature, src_loc=src_loc, line_number_start=start, line_number_end=end, module_id=module_id))

    # Classes
    classes_data = [
        (1, 'MyClass', 'class MyClass...', 'src_loc_1', 1, 10, 1327)
    ]
    for id, name, definition, src_loc, start, end, module_id in classes_data:
        session.add(Class(id=id, class_name=name, class_definition=definition, src_location=src_loc, line_number_start=start, line_number_end=end, module_id=module_id))

    # Imports
    imports_data = [
        (1, 'storage_impl', None, 'crates/storage_impl/src/metrics.rs', False, None, None, None, None, False, None, 1, 1, 1327)
    ]
    for id, mod_name, pkg_name, src_loc, boot, safe, implicit, as_name, qual, hiding, specs, start, end, mod_id in imports_data:
        session.add(Import(id=id, module_name=mod_name, package_name=pkg_name, src_loc=src_loc, is_boot_source=boot, is_safe=safe, is_implicit=implicit, as_module_name=as_name, qualified_style=qual, is_hiding=hiding, hiding_specs=specs, line_number_start=start, line_number_end=end, module_id=mod_id))

    session.commit()

class TestManualQueriesPart6(unittest.TestCase):
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

    def test_qs_022_get_instances_per_module(self):
        print("\\n--- Testing QS-022: get_instances_per_module ---")
        results = self.query_service.get_instances_per_module('storage_impl')
        print(f"Found {len(results)} instances for module 'storage_impl'.")
        self.assertEqual(len(results), 2)

    def test_qs_036_get_classes_by_module(self):
        print("\\n--- Testing QS-036: get_classes_by_module ---")
        results = self.query_service.get_classes_by_module(1327)
        print(f"Found {len(results)} classes for module 1327.")
        self.assertEqual(len(results), 1)

    def test_qs_037_get_imports_by_module(self):
        print("\\n--- Testing QS-037: get_imports_by_module ---")
        results = self.query_service.get_imports_by_module(1327)
        print(f"Found {len(results)} imports for module 1327.")
        self.assertEqual(len(results), 1)

    def test_qs_038_get_instances_by_module(self):
        print("\\n--- Testing QS-038: get_instances_by_module ---")
        results = self.query_service.get_instances_by_module(1327)
        print(f"Found {len(results)} instances for module 1327.")
        self.assertEqual(len(results), 2)

if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
