import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from code_as_data.services.query_service import QueryService
from code_as_data.db.models import Base, Module, Type

def populate_test_data(session):
    # Modules
    modules_data = [
        (1837, 'storage_impl::payouts::payout_attempt', 'crates/storage_impl/src/payouts/payout_attempt.rs')
    ]
    for id, name, path in modules_data:
        session.add(Module(id=id, name=name, path=path))

    # Types
    types_data = [
        (1, 'StorageModel', 'crates/storage_impl/src/callback_mapper.rs', 'data', 7, 7, 1837),
        (2, 'StorageModel', 'crates/storage_impl/src/callback_mapper.rs', 'data', 7, 7, 1837),
        (3, 'StorageResult', 'crates/storage_impl/src/errors.rs', 'type_alias', 5, 5, 1837)
    ]
    for id, type_name, raw_code, type_of_type, line_number_start, line_number_end, module_id in types_data:
        session.add(Type(id=id, type_name=type_name, raw_code=raw_code, type_of_type=type_of_type, line_number_start=line_number_start, line_number_end=line_number_end, module_id=module_id))

    session.commit()


class TestManualQueriesPart2(unittest.TestCase):
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

    def test_qs_035_get_types_by_module(self):
        print("\\n--- Testing QS-035: get_types_by_module ---")
        results = self.query_service.get_types_by_module(1837)
        print(f"Found {len(results)} types for module 1837.")
        for t in results:
            print(f"  - {t.__dict__}")
        self.assertGreater(len(results), 0)

    def test_qs_039_get_type_by_name(self):
        print("\\n--- Testing QS-039: get_type_by_name ---")
        result = self.query_service.get_type_by_name('StorageModel')
        print(f"Found type: {result.__dict__ if result else 'None'}")
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
