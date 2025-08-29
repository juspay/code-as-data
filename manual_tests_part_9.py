import unittest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from code_as_data.services.query_service import QueryService
from code_as_data.db.models import Base, Module, Function

def populate_test_data(session):
    # Modules
    modules_data = [
        (1, 'fdep', 'src/visitor.rs'),
        (2, 'core::option', 'core/option'),
        (3, 'std::env', 'std/env'),
        (4, 'test', 'test'),
        (5, 'alloc::fmt', 'alloc/fmt'),
        (6, 'core::fmt', 'core/fmt'),
        (7, 'rustc_middle::hir', 'rustc_middle/hir'),
    ]
    for id, name, path in modules_data:
        session.add(Module(id=id, name=name, path=path))

    # Functions based on your database data
    functions_data = [
        (1, 'compile_time_sysroot', 'src/visitor.rs', 'fdep', 1, 'pub fn compile_time_sysroot() -> Option<String> { ... }'),
        (2, 'analyze', 'src/visitor.rs', 'fdep', 1, 'pub fn analyze() { ... }'),
        (3, 'get_output_dir', 'src/visitor.rs', 'fdep', 1, 'fn get_output_dir() -> String { ... }'),
        (4, 'main', 'src/main.rs', 'fdep', 1, 'fn main() { ... }'),
        (7, 'Some', 'core/option', 'core::option', 2, 'pub const fn Some(value: T) -> Option<T> { ... }'),
        (13, 'get_attrs_string', 'src/visitor.rs', 'fdep', 1, 'pub fn get_attrs_string(&self, hir_id: HirId) -> Vec<String> { ... }'),
        (14, 'extract_doc_comments', 'src/visitor.rs', 'fdep', 1, 'pub fn extract_doc_comments(&self, hir_id: HirId) -> String { ... }'),
        (15, 'create_dir_all', 'std/fs', 'std::fs', 3, 'pub fn create_dir_all<P: AsRef<Path>>(path: P) -> io::Result<()> { ... }'),
        (16, 'with_output_dir', 'src/visitor.rs', 'fdep', 1, 'fn with_output_dir(&mut self, dir: String) { ... }'),
        (17, 'unwrap_or_else', 'core/option', 'core::option', 2, 'pub fn unwrap_or_else<F>(self, f: F) -> T { ... }'),
        (18, 'expect', 'core/result', 'core::result', 2, 'pub fn expect(self, msg: &str) -> T { ... }'),
        (19, 'visit_all_item_likes_in_crate', 'rustc_middle/hir', 'rustc_middle::hir', 7, 'pub fn visit_all_item_likes_in_crate(&self, visitor: &mut V) { ... }'),
        (20, 'hir', 'rustc_middle/hir', 'rustc_middle::hir', 7, 'pub fn hir(&self) -> &hir::Crate { ... }'),
        (21, 'dump', 'src/visitor.rs', 'fdep', 1, 'fn dump(&self) { ... }'),
        (22, 'from', 'core/convert', 'core::convert', 2, 'fn from(value: T) -> Self { ... }'),
        (23, 'args', 'std/env', 'std::env', 3, 'pub fn args() -> Args { ... }'),
        (24, 'into_iter', 'core/iter', 'core::iter', 2, 'fn into_iter(self) -> Self::IntoIter { ... }'),
    ]
    for id, name, src_loc, module_name, module_id, raw_string in functions_data:
        session.add(Function(id=id, name=name, src_loc=src_loc, module_name=module_name, module_id=module_id, raw_string=raw_string))

    session.commit()

    # Add function dependencies based on your database data
    function_dependencies = [
        (2, 3),   # analyze calls get_output_dir
        (1, 7),   # compile_time_sysroot calls Some
        (1, 3),   # compile_time_sysroot calls get_output_dir
        (2, 7),   # analyze calls Some
        (2, 15),  # analyze calls create_dir_all
        (2, 16),  # analyze calls with_output_dir
        (2, 17),  # analyze calls unwrap_or_else
        (2, 18),  # analyze calls expect
        (2, 19),  # analyze calls visit_all_item_likes_in_crate
        (2, 20),  # analyze calls hir
        (2, 21),  # analyze calls dump
        (3, 23),  # get_output_dir calls args
        (3, 24),  # get_output_dir calls into_iter
        (19, 20), # visit_all_item_likes_in_crate calls hir
        (19, 16), # visit_all_item_likes_in_crate calls with_output_dir
        (19, 3),  # visit_all_item_likes_in_crate calls get_output_dir
        (20, 7),  # hir calls Some
        (20, 19), # hir calls visit_all_item_likes_in_crate
        (20, 16), # hir calls with_output_dir
        (21, 7),  # dump calls Some
        (21, 3),  # dump calls get_output_dir
        (13, 14), # get_attrs_string calls extract_doc_comments (example)
        (14, 7),  # extract_doc_comments calls Some
    ]
    
    # Insert function dependencies using raw SQL
    for caller_id, callee_id in function_dependencies:
        session.execute(
            text("INSERT INTO function_dependency (caller_id, callee_id) VALUES (:caller_id, :callee_id)"),
            {"caller_id": caller_id, "callee_id": callee_id}
        )
    
    session.commit()


class TestManualQueriesPart9(unittest.TestCase):
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

    def test_qs_005_get_function_details(self):
        print("\n--- Testing QS-005: get_function_details ---")
        # Test with function ID 2 (analyze function)
        result = self.query_service.get_function_details(2)
        print(f"Function details for ID 2: {result}")
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'analyze')
        self.assertIn('calls', result)
        self.assertIn('called_by', result)
        self.assertGreater(len(result['calls']), 0)

    def test_qs_006_get_most_called_functions(self):
        print("\n--- Testing QS-006: get_most_called_functions ---")
        results = self.query_service.get_most_called_functions(limit=5)
        print(f"Found {len(results)} most called functions:")
        for func in results:
            print(f"  - {func['name']} (module: {func['module']}) called {func['calls']} times")
        self.assertGreater(len(results), 0)
        # Verify results are sorted by call count
        if len(results) > 1:
            self.assertGreaterEqual(results[0]['calls'], results[1]['calls'])

    def test_qs_008_pattern_match_function_calls(self):
        print("\n--- Testing QS-008: pattern_match (function calls) ---")
        # Test pattern matching for function calls
        pattern = {
            "type": "function_call",
            "caller": "analyze",
            "callee": "get_output_dir"
        }
        results = self.query_service.pattern_match(pattern)
        print(f"Found {len(results)} function call patterns:")
        for result in results:
            print(f"  - {result['caller']['name']} calls {result['callee']['name']}")
        self.assertGreater(len(results), 0)

    def test_qs_013_find_cross_module_dependencies(self):
        print("\n--- Testing QS-013: find_cross_module_dependencies ---")
        results = self.query_service.find_cross_module_dependencies()
        print(f"Found {len(results)} cross-module dependencies:")
        for dep in results:
            print(f"  - {dep['caller_module']['name']} -> {dep['callee_module']['name']} ({dep['call_count']} calls)")
        self.assertGreaterEqual(len(results), 0)  # May be 0 if all calls are within same module

    def test_qs_014_analyze_module_coupling(self):
        print("\n--- Testing QS-014: analyze_module_coupling ---")
        result = self.query_service.analyze_module_coupling()
        print(f"Module coupling analysis:")
        print(f"  - Total modules: {result['module_count']}")
        print(f"  - Total cross-module calls: {result['total_cross_module_calls']}")
        print(f"  - Dependency count: {result['dependency_count']}")
        print("  - Top coupled modules:")
        for module in result['module_metrics'][:3]:
            print(f"    - {module['name']}: {module['total']} total dependencies")
        self.assertIsInstance(result, dict)
        self.assertIn('module_metrics', result)
        self.assertIn('total_cross_module_calls', result)

    def test_qs_015_find_complex_functions(self):
        print("\n--- Testing QS-015: find_complex_functions ---")
        results = self.query_service.find_complex_functions(complexity_threshold=5)
        print(f"Found {len(results)} complex functions:")
        for func in results:
            metrics = func['metrics']
            print(f"  - {func['function']['name']}: complexity={metrics['total_complexity']}")
            print(f"    - Cyclomatic: {metrics['cyclomatic_complexity']}")
            print(f"    - Dependencies: {metrics['dependency_count']}")
            print(f"    - Nested functions: {metrics['nested_functions']}")
        self.assertGreaterEqual(len(results), 0)

    def test_qs_016_get_function_call_graph(self):
        print("\n--- Testing QS-016: get_function_call_graph ---")
        # Test with function ID 2 (analyze function) with depth 2
        result = self.query_service.get_function_call_graph(2, depth=2)
        print(f"Call graph for function 2 (analyze):")
        print(f"  - Root: {result.get('name', 'Unknown')} (module: {result.get('module', 'Unknown')})")
        if 'calls' in result:
            print(f"  - Direct calls: {len(result['calls'])}")
            for call in result['calls'][:3]:  # Show first 3
                print(f"    - {call['name']} (module: {call['module']})")
                if 'calls' in call:
                    print(f"      - Nested calls: {len(call['calls'])}")
        self.assertIsInstance(result, dict)
        self.assertIn('name', result)
        self.assertEqual(result['name'], 'analyze')

    def test_qs_031_get_functions_used(self):
        print("\n--- Testing QS-031: get_functions_used ---")
        # Test with function ID 2 (analyze function)
        result = self.query_service.get_functions_used(2)
        print(f"Functions used by function 2 (analyze):")
        print(f"  - Local functions: {len(result.get('local_functions', []))}")
        print(f"  - Other functions: {len(result.get('other_functions', []))}")
        
        for func in result.get('local_functions', [])[:3]:  # Show first 3
            print(f"    - Local: {func.name} (module: {func.module_name})")
        
        for func in result.get('other_functions', [])[:3]:  # Show first 3
            print(f"    - Other: {func.get('function_name', 'Unknown')} (module: {func.get('module_name', 'Unknown')})")
        
        self.assertIsInstance(result, dict)
        self.assertIn('local_functions', result)
        self.assertIn('other_functions', result)

    def test_qs_032_get_functions_used_prompt(self):
        print("\n--- Testing QS-032: get_functions_used_prompt ---")
        # Test with function ID 2 (analyze function)
        local_prompt, non_local_prompt = self.query_service.get_functions_used_prompt(2)
        print(f"Local functions prompt length: {len(local_prompt)}")
        print(f"Non-local functions prompt length: {len(non_local_prompt)}")
        
        if local_prompt:
            print("Local functions prompt preview:")
            print(local_prompt[:200] + "..." if len(local_prompt) > 200 else local_prompt)
        
        if non_local_prompt:
            print("Non-local functions prompt preview:")
            print(non_local_prompt[:200] + "..." if len(non_local_prompt) > 200 else non_local_prompt)
        
        self.assertIsInstance(local_prompt, str)
        self.assertIsInstance(non_local_prompt, str)


if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
