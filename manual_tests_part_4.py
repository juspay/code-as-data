import unittest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from code_as_data.services.query_service import QueryService
from code_as_data.db.models import Base, Module, Trait, ImplBlock, Constant, TraitMethodSignature, Function, Type

def populate_test_data(session):
    # Modules
    modules_data = [
        (808, 'unknown::unknown', 'crates/storage_impl/src/callback_mapper.rs'),
        (1327, 'storage_impl', 'crates/storage_impl/src/metrics.rs'),
        (1048, 'storage_impl::payouts::payout_attempt', 'crates/storage_impl/src/payouts/payout_attempt.rs')
    ]
    for id, name, path in modules_data:
        session.add(Module(id=id, name=name, path=path))

    # Functions
    functions_data = [
        (1, 'to_storage_model', 'crates/storage_impl/src/payouts/payout_attempt.rs', 'storage_impl::payouts::payout_attempt', 1048, 1)
    ]
    for id, name, src_loc, module_name, module_id, impl_block_id in functions_data:
        session.add(Function(id=id, name=name, src_loc=src_loc, module_name=module_name, module_id=module_id, impl_block_id=impl_block_id))

    # Traits
    traits_data = [
        (1, 'DataModelExt', 'unknown::unknown::DataModelExt', 'crates/storage_impl/src/callback_mapper.rs', 'unknown::unknown', 808, 'unknown', 'unknown'),
        (2, 'Debug', 'unknown::unknown::Debug', 'crates/storage_impl/src/errors.rs', 'unknown::unknown', 808, 'unknown', 'unknown')
    ]
    for id, name, fqp, src_loc, mod_name, mod_id, mod_path, crate in traits_data:
        session.add(Trait(id=id, name=name, fully_qualified_path=fqp, src_location=src_loc, module_name=mod_name, module_id=mod_id, module_path=mod_path, crate_name=crate))

    # Impl Blocks
    impl_blocks_data = [
        (1, 'CallbackMapper', 'hyperswitch_domain_models::callback_mapper::CallbackMapper', 'DataModelExt', 'unknown::unknown::DataModelExt', 'crates/storage_impl/src/callback_mapper.rs', 1327, 1),
        (2, 'StorageError', 'storage_impl::errors::StorageError', 'Debug', 'unknown::unknown::Debug', 'crates/storage_impl/src/errors.rs', 1327, 2)
    ]
    for id, struct_name, struct_fqp, trait_name, trait_fqp, src_loc, mod_id, trait_id in impl_blocks_data:
        session.add(ImplBlock(id=id, struct_name=struct_name, struct_fqp=struct_fqp, trait_name=trait_name, trait_fqp=trait_fqp, src_location=src_loc, module_id=mod_id, trait_id=trait_id))

    # Constants
    constants_data = [
        (1, '_', 'storage_impl::_', '{"type_name": "()", "crate_name": "core", "module_path": "tuple", "generic_args": [], "is_generic_param": false, "src_location": "crates/storage_impl/src/config.rs"}', 'crates/storage_impl/src/config.rs', 'serde::Deserialize', 4, 4, 1327, 'pub(config)', '#[derive(Debug)]', False),
        (2, 'FIELDS', 'storage_impl::FIELDS', '{"type_name": "&[&str]", "crate_name": "core", "module_path": "slice", "generic_args": [{"type_name": "&str", "crate_name": "core", "module_path": "primitive", "generic_args": [], "is_generic_param": false, "src_location": "crates/storage_impl/src/config.rs"}], "is_generic_param": false, "src_location": "crates/storage_impl/src/config.rs"}', 'crates/storage_impl/src/config.rs', 'serde::Deserialize', 4, 4, 1327, 'pub(config)', '#[derive(Clone)]', False)
    ]
    for id, name, fqp, const_type, src_loc, src_code, start, end, mod_id, visibility, attrs, is_static in constants_data:
        session.add(Constant(id=id, name=name, fully_qualified_path=fqp, const_type=const_type, src_location=src_loc, src_code=src_code, line_number_start=start, line_number_end=end, module_id=mod_id, visibility=visibility, attributes=attrs, is_static=is_static))

    session.commit()

class TestManualQueriesPart4(unittest.TestCase):
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

    def test_qs_042_get_methods_for_struct(self):
        print("\\n--- Testing QS-042: get_methods_for_struct ---")
        results = self.query_service.get_methods_for_struct('CallbackMapper')
        print(f"Found {len(results)} methods for struct 'CallbackMapper'.")
        for r in results:
            print(f"  - {r.__dict__}")
        self.assertEqual(len(results), 1)

    def test_qs_043_get_all_traits(self):
        print("\\n--- Testing QS-043: get_all_traits ---")
        results = self.query_service.get_all_traits()
        print(f"Found {len(results)} traits.")
        for t in results:
            print(f"  - {t.__dict__}")
        self.assertEqual(len(results), 2)

    def test_qs_044_get_trait_by_id(self):
        print("\\n--- Testing QS-044: get_trait_by_id ---")
        result = self.query_service.get_trait_by_id(1)
        print(f"Found trait: {result.__dict__ if result else 'None'}")
        self.assertIsNotNone(result)

    def test_qs_045_get_all_impl_blocks(self):
        print("\\n--- Testing QS-045: get_all_impl_blocks ---")
        results = self.query_service.get_all_impl_blocks()
        print(f"Found {len(results)} impl blocks.")
        for i in results:
            print(f"  - {i.__dict__}")
        self.assertEqual(len(results), 2)

    def test_qs_047_get_all_constants(self):
        print("\\n--- Testing QS-047: get_all_constants ---")
        results = self.query_service.get_all_constants()
        print(f"Found {len(results)} constants.")
        for c in results:
            print(f"  - {c.__dict__}")
        self.assertEqual(len(results), 2)

    def test_qs_051_find_by_fully_qualified_path(self):
        print("\\n--- Testing QS-051: find_by_fully_qualified_path ---")
        results = self.query_service.find_by_fully_qualified_path('unknown::unknown::DataModelExt')
        print(f"Found {len(results)} entities with fqp 'unknown::unknown::DataModelExt'.")
        for r in results:
            print(f"  - {r.__dict__}")
        self.assertEqual(len(results), 1)

    def test_qs_052_find_by_visibility(self):
        print("\\n--- Testing QS-052: find_by_visibility ---")
        results = self.query_service.find_by_visibility('constant', 'pub(config)')
        print(f"Found {len(results)} constants with visibility 'pub(config)'.")
        for r in results:
            print(f"  - {r.__dict__}")
        self.assertEqual(len(results), 2)

    def test_qs_053_find_by_crate(self):
        print("\\n--- Testing QS-053: find_by_crate ---")
        results = self.query_service.find_by_crate('trait', 'unknown')
        print(f"Found {len(results)} traits in crate 'unknown'.")
        for r in results:
            print(f"  - {r.__dict__}")
        self.assertEqual(len(results), 2)

    def test_qs_056_find_entities_with_attribute(self):
        print("\\n--- Testing QS-056: find_entities_with_attribute ---")
        results = self.query_service.find_entities_with_attribute('constant', '#[derive(Debug)]')
        print(f"Found {len(results)} constants with attribute '#[derive(Debug)]'.")
        for r in results:
            print(f"  - {r.__dict__}")
        self.assertEqual(len(results), 1)

if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
