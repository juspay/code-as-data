import argparse
from code_as_data.models.type_model import *
from code_as_data.models.class_model import *
from code_as_data.models.function_model import *
from code_as_data.models.import_model import *
from code_as_data.models.instance_model import *
from code_as_data.parsers.class_parser import *
from code_as_data.parsers.function_parser import *
from code_as_data.parsers.import_parser import *
from code_as_data.parsers.instance_parser import *
from code_as_data.parsers.type_parser import *
from code_as_data.db.neo4j_connection import Neo4jConnection
from code_as_data.ingestion.neo4j_ingest import *

def import_dumps(fdep_path):
    print(f"Starting Neo4j ingestion process from fdep_path: {fdep_path}")

    if not os.path.exists(fdep_path):
        print(f"Error: fdep_path '{fdep_path}' does not exist. Please configure it correctly.")
        return

    # Establish Neo4j connection
    driver = Neo4jConnection.get_driver()
    if not driver:
        print("Failed to connect to Neo4j. Aborting.")
        exit()

    create_constraints()

    # Initialize parsers
    print("Initializing parsers...")
    class_parser = ClassParser(json_path=fdep_path)
    function_parser = FunctionParser(fdep_path=fdep_path)
    import_parser = ImportParser(raw_code_path=fdep_path)
    # InstanceParser needs module_vs_functions, load functions first
    type_parser = TypeParser(raw_code_path=fdep_path)

    # Load data
    print("Loading data from parsers...")
    all_classes = class_parser.load()
    print(f"Loaded {sum(len(v) for v in all_classes.values())} classes.")

    all_functions = function_parser.load() # This is Dict[str, List[Function]]
    print(f"Loaded {sum(len(v) for v in all_functions.values())} top-level functions.")

    all_imports = import_parser.load()
    print(f"Loaded {sum(len(v) for v in all_imports.values())} import records.")

    instance_parser = InstanceParser(path=fdep_path, base_dir_path=fdep_path, module_vs_functions=all_functions)
    all_instances = instance_parser.load_all_files() # Corrected method name
    print(f"Loaded {sum(len(v) for v in all_instances.values())} instances.")

    all_types = type_parser.load()
    print(f"Loaded {sum(len(v) for v in all_types.values())} types.")

    # Collect all module names
    module_names: Set[str] = set()
    for data_dict in [all_classes, all_functions, all_imports, all_instances, all_types]:
        module_names.update(data_dict.keys())

    # Add module names from imported modules as well
    for imports_in_module in all_imports.values():
        for imp in imports_in_module:
            if imp.module_name:
                module_names.add(imp.module_name)

    # Phase 1: Node Ingestion & Basic Module Links
    print("\n--- Phase 1: Node Ingestion & Basic Module Links ---")
    ingest_modules(module_names)
    ingest_classes(all_classes)
    ingest_types(all_types) # Ingests Types, Constructors, Fields
    ingest_functions(all_functions) # Ingests Functions and WhereFunctions
    ingest_instances(all_instances)
    ingest_imports(all_imports) # Ingests ImportRecord nodes

    # Phase 2: Relationship Ingestion
    print("\n--- Phase 2: Detailed Relationship Ingestion ---")
    ingest_import_links(all_imports)
    ingest_function_relationships(all_functions) # CALLS, DEFINES_WHERE, USES_INSTANCE_SIGNATURE
    ingest_instance_relationships(all_instances) # IMPLEMENTS
    ingest_field_type_relationships(all_types) # HAS_ATOMIC_TYPE for Fields

    print("\nNeo4j ingestion process completed.")
    Neo4jConnection.close_driver()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import dump files into the database")
    parser.add_argument("fdep_path", help="Path to the fdep files")
    parser.add_argument(
        "--clear", action="store_true", help="Clear the database before importing"
    )

    args = parser.parse_args()
    import_dumps(args.fdep_path)