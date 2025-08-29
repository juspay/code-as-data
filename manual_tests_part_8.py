import unittest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from code_as_data.services.query_service import QueryService
from code_as_data.db.models import Base, Module, Function

def populate_test_data(session):
    # Modules
    modules_data = [
        (1048, 'storage_impl::payouts::payout_attempt', 'crates/storage_impl/src/payouts/payout_attempt.rs'),
        (31, 'storage_impl::redis::kv_store', 'crates/storage_impl/src/redis/kv_store.rs'),
        (1430, 'storage_impl::redis::cache', 'crates/storage_impl/src/redis/cache.rs'),
        (1295, 'storage_impl::errors', 'crates/storage_impl/src/errors.rs'),
        (1167, 'storage_impl::config', 'crates/storage_impl/src/config.rs')
    ]
    for id, name, path in modules_data:
        session.add(Module(id=id, name=name, path=path))

    # Functions
    functions_data = [
        (1, 'to_storage_model', 'crates/storage_impl/src/payouts/payout_attempt.rs', 'storage_impl::payouts::payout_attempt', 1048, 'fn to_storage_model...'),
        (2, 'from_storage_model', 'crates/storage_impl/src/payouts/payout_attempt.rs', 'storage_impl::payouts::payout_attempt', 1048, 'fn from_storage_model...'),
        (6, 'is_db_unique_violation', 'crates/storage_impl/src/errors.rs', 'storage_impl::errors', 1295, 'pub fn is_db_unique_violation...'),
        (7, 'to_redis_failed_response', 'crates/storage_impl/src/errors.rs', 'storage_impl::errors', 1295, 'fn to_redis_failed_response...'),
        (10, 'deserialize', 'crates/storage_impl/src/redis/cache.rs', 'storage_impl::redis::cache', 1430, 'serde::Deserialize'),
        (11, 'expecting', 'crates/storage_impl/src/redis/cache.rs', 'storage_impl::redis::cache', 1430, 'serde::Deserialize'),
        (12, 'visit_u64', 'crates/storage_impl/src/redis/cache.rs', 'storage_impl::redis::cache', 1430, 'serde::Deserialize'),
    ]
    for id, name, src_loc, module_name, module_id, raw_string in functions_data:
        session.add(Function(id=id, name=name, src_loc=src_loc, module_name=module_name, module_id=module_id, raw_string=raw_string))

    session.commit()

class TestManualQueriesPart8(unittest.TestCase):
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

    def test_qs_010_find_similar_functions(self):
        print("\\n--- Testing QS-010: find_similar_functions ---")
        # Using function 10 which has raw_string 'serde::Deserialize'
        results = self.query_service.find_similar_functions(10, threshold=0.9)
        print(f"Found {len(results)} functions similar to function 10.")
        self.assertGreaterEqual(len(results), 2)

    def test_qs_012_group_similar_functions(self):
        print("\\n--- Testing QS-012: group_similar_functions ---")
        results = self.query_service.group_similar_functions(similarity_threshold=0.9)
        print(f"Found {len(results)} groups of similar functions.")
        self.assertGreaterEqual(len(results), 1)

if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
