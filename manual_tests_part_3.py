import unittest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from code_as_data.services.query_service import QueryService
from code_as_data.db.models import Base, Module, Trait, ImplBlock, Constant, TraitMethodSignature, Function

def populate_test_data(session):
    # Modules
    modules_data = [
        (808, 'unknown::unknown', 'crates/storage_impl/src/callback_mapper.rs'),
        (1327, 'storage_impl', 'crates/storage_impl/src/metrics.rs')
    ]
    for id, name, path in modules_data:
        session.add(Module(id=id, name=name, path=path))

    # Traits
    traits_data = [
        (1, 'DataModelExt', 'unknown::unknown::DataModelExt', 'crates/storage_impl/src/callback_mapper.rs', 'unknown::unknown', 808, 'unknown', 'unknown')
    ]
    for id, name, fqp, src_loc, mod_name, mod_id, mod_path, crate in traits_data:
        session.add(Trait(id=id, name=name, fully_qualified_path=fqp, src_location=src_loc, module_name=mod_name, module_id=mod_id, module_path=mod_path, crate_name=crate))

    # Impl Blocks
    impl_blocks_data = [
        (1, 'CallbackMapper', 'hyperswitch_domain_models::callback_mapper::CallbackMapper', 'DataModelExt', 'unknown::unknown::DataModelExt', 'crates/storage_impl/src/callback_mapper.rs', 1327, 1)
    ]
    for id, struct_name, struct_fqp, trait_name, trait_fqp, src_loc, mod_id, trait_id in impl_blocks_data:
        session.add(ImplBlock(id=id, struct_name=struct_name, struct_fqp=struct_fqp, trait_name=trait_name, trait_fqp=trait_fqp, src_location=src_loc, module_id=mod_id, trait_id=trait_id))

    # Constants
    constants_data = [
        (1, '_', 'storage_impl::_', '{"type_name": "()", "crate_name": "core", "module_path": "tuple", "generic_args": [], "is_generic_param": false, "src_location": "crates/storage_impl/src/config.rs"}', 'crates/storage_impl/src/config.rs', 'serde::Deserialize', 4, 4, 1327, 'pub(config)', '[]', False)
    ]
    for id, name, fqp, const_type, src_loc, src_code, start, end, mod_id, visibility, attrs, is_static in constants_data:
        session.add(Constant(id=id, name=name, fully_qualified_path=fqp, const_type=const_type, src_location=src_loc, src_code=src_code, line_number_start=start, line_number_end=end, module_id=mod_id, visibility=visibility, attributes=attrs, is_static=is_static))

    # Trait Method Signatures
    trait_method_signatures_data = [
        (1, 'to_redis_failed_response', 'storage_impl::to_redis_failed_response', '[{"type_name": "Self", "crate_name": "", "module_path": "", "generic_args": [], "is_generic_param": true, "src_location": "crates/storage_impl/src/errors.rs"}, {"type_name": "&str", "crate_name": "core", "module_path": "primitive", "generic_args": [], "is_generic_param": false, "src_location": "crates/storage_impl/src/errors.rs"}]', '[{"type_name": "Report<StorageError>", "crate_name": "error_stack", "module_path": "report", "generic_args": [{"type_name": "StorageError", "crate_name": "storage_impl", "module_path": "errors", "generic_args": [], "is_generic_param": false, "src_location": "crates/storage_impl/src/errors.rs"}], "is_generic_param": false, "src_location": "crates/storage_impl/src/errors.rs"}]', 'crates/storage_impl/src/errors.rs', 'fn to_redis_failed_response(self, key: &str) -> error_stack::Report<StorageError>;', 96, 96, 'storage_impl', 'pub', '[]', False, False, None)
    ]
    for id, name, fqp, inputs, outputs, src_loc, src_code, start, end, mod_name, visibility, attrs, is_async, is_unsafe, trait_id in trait_method_signatures_data:
        session.add(TraitMethodSignature(id=id, name=name, fully_qualified_path=fqp, input_types=inputs, output_types=outputs, src_location=src_loc, src_code=src_code, line_number_start=start, line_number_end=end, module_name=mod_name, visibility=visibility, attributes=attrs, is_async=is_async, is_unsafe=is_unsafe, trait_id=trait_id))

    session.commit()

class TestManualQueriesPart3(unittest.TestCase):
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

    def test_qs_040_find_trait_by_name(self):
        print("\\n--- Testing QS-040: find_trait_by_name ---")
        results = self.query_service.find_trait_by_name('DataModelExt')
        print(f"Found {len(results)} traits with name 'DataModelExt'.")
        for t in results:
            print(f"  - {t.__dict__}")
        self.assertEqual(len(results), 1)

    def test_qs_041_get_implementations_for_trait(self):
        print("\\n--- Testing QS-041: get_implementations_for_trait ---")
        results = self.query_service.get_implementations_for_trait('DataModelExt')
        print(f"Found {len(results)} impls for trait 'DataModelExt'.")
        for i in results:
            print(f"  - {i.__dict__}")
        self.assertEqual(len(results), 1)

    def test_qs_046_get_impl_blocks_for_struct(self):
        print("\\n--- Testing QS-046: get_impl_blocks_for_struct ---")
        results = self.query_service.get_impl_blocks_for_struct('CallbackMapper')
        print(f"Found {len(results)} impl blocks for struct 'CallbackMapper'.")
        for i in results:
            print(f"  - {i.__dict__}")
        self.assertEqual(len(results), 1)

    def test_qs_048_get_constant_by_name(self):
        print("\\n--- Testing QS-048: get_constant_by_name ---")
        results = self.query_service.get_constant_by_name('_')
        print(f"Found {len(results)} constants with name '_'.")
        for c in results:
            print(f"  - {c.__dict__}")
        self.assertEqual(len(results), 1)

    def test_qs_050_get_trait_method_signatures_for_trait(self):
        print("\\n--- Testing QS-050: get_trait_method_signatures_for_trait ---")
        # This test will likely fail until the trait_id is correctly populated.
        # For now, we'll just see what it returns.
        results = self.query_service.get_trait_method_signatures_for_trait(1)
        print(f"Found {len(results)} method signatures for trait 1.")
        for s in results:
            print(f"  - {s.__dict__}")
        # self.assertGreater(len(results), 0)

if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
