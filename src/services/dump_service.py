from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Dict, List, Optional, Any, Union
import time
import os
import csv
import json
import tempfile
import shutil
from sqlalchemy.orm import Session
from sqlalchemy import text
from contextlib import contextmanager

from src.db.connection import SessionLocal
from src.db.repository import Repository
from src.parsers.function_parser import FunctionParser
from src.parsers.class_parser import ClassParser
from src.parsers.import_parser import ImportParser
from src.parsers.type_parser import TypeParser
from src.parsers.instance_parser import InstanceParser
from src.models.function_model import Function
from src.models.class_model import Class
from src.models.import_model import Import
from src.models.type_model import Type
from src.models.instance_model import Instance
import concurrent.futures

MAX_RETRIES = 3
RETRY_DELAY = 2  # Seconds between retries
TIMEOUT = 10  # Timeout in seconds for each session creation


class DumpService:
    """Service for handling dump file processing and database insertion."""

    def __init__(self, fdep_path: str, field_inspector_path: str):
        """
        Initialize the dump service.

        Args:
            fdep_path: Path to the fdep files
            field_inspector_path: Path to the field inspector files
        """
        self.fdep_path = fdep_path
        self.field_inspector_path = field_inspector_path
        self.repository = Repository()

        # Initialize parsers
        self.function_parser = FunctionParser(fdep_path)
        self.class_parser = ClassParser(field_inspector_path)
        self.import_parser = ImportParser(fdep_path, fdep_path)
        self.type_parser = TypeParser(fdep_path, field_inspector_path)

        # For optimized bulk loading
        self.temp_dir = None
        self.module_id_map = {}
        self.function_id_map = {}
        self.class_id_map = {}
        self.type_id_map = {}
        self.constructor_id_map = {}
        self.instance_id_map = {}
        self.csv_files = {}

    @contextmanager
    def get_session(self):
        """
        Get a database session with retry logic.
        """
        attempt = 0
        session = None
        while attempt < MAX_RETRIES:
            try:
                session = SessionLocal()
                # Optimize session for bulk operations
                session.execute(text("SET synchronous_commit = off"))
                session.execute(text("SET work_mem = '256MB'"))
                session.execute(text("SET maintenance_work_mem = '1GB'"))
                session.execute(text("SET statement_timeout = 3600000"))  # 1 hour
                session.execute(text("SET temp_buffers = '256MB'"))
                session.execute(text("SET client_min_messages = 'warning'"))
                break
            except Exception as e:
                print(
                    f"Attempt {attempt + 1}/{MAX_RETRIES} failed to create session: {e}"
                )
                attempt += 1
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    raise Exception("Max retries reached, unable to create session.")

        try:
            yield session
        except Exception as e:
            if session:
                session.rollback()
            raise e
        finally:
            if session:
                session.close()

    def process_functions(self) -> Dict[str, List[Function]]:
        """
        Process function dump files and return the parsed data.

        Returns:
            Dictionary of module names to functions
        """
        # Load function data
        self.function_parser.load_all_files()

        # Get functions as domain models
        functions = self.function_parser.get_functions()

        # Group functions by module
        functions_by_module = {}
        for function in functions:
            if function.module_name not in functions_by_module:
                functions_by_module[function.module_name] = []
            functions_by_module[function.module_name].append(function)

        return functions_by_module

    def process_classes(self) -> Dict[str, List[Class]]:
        """
        Process class dump files and return the parsed data.

        Returns:
            Dictionary of module names to classes
        """
        return self.class_parser.load()

    def process_imports(self) -> Dict[str, List[Import]]:
        """
        Process import dump files and return the parsed data.

        Returns:
            Dictionary of module names to imports
        """
        return self.import_parser.load()

    def process_types(self) -> Dict[str, List[Type]]:
        """
        Process type dump files and return the parsed data.

        Returns:
            Dictionary of module names to types
        """
        return self.type_parser.load()

    def process_instances(
        self, module_vs_functions: Dict[str, List[Function]]
    ) -> Dict[str, List[Instance]]:
        """
        Process instance dump files and return the parsed data.

        Args:
            module_vs_functions: Dictionary of modules to their functions

        Returns:
            Dictionary of module names to instances
        """
        instance_parser = InstanceParser(
            self.fdep_path, self.fdep_path, module_vs_functions
        )
        return instance_parser.load_all_files()

    def prepare_csv_file(self, table_name, columns):
        """Create and prepare a CSV file for a specific table."""
        file_path = os.path.join(self.temp_dir, f"{table_name}.csv")
        csv_file = open(file_path, "w", newline="")
        csv_writer = csv.writer(
            csv_file, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL
        )
        csv_writer.writerow(columns)

        self.csv_files[table_name] = {
            "path": file_path,
            "columns": columns,
            "file": csv_file,
            "writer": csv_writer,
        }
        return csv_writer

    def prepare_database(self):
        """Prepare the database for high-speed inserts by temporarily disabling constraints and indexes."""
        with self.get_session() as db:
            print("Preparing database for high-speed inserts...")
            try:
                # Start transaction
                db.execute(text("BEGIN"))

                # Temporarily disable triggers
                db.execute(text("SET session_replication_role = 'replica'"))

                # Optional: Drop existing indexes if you're completely rebuilding data
                # DO NOT drop primary key constraints/indexes
                # db.execute(text("DROP INDEX IF EXISTS idx_function_name"))
                # Add more index drops here if needed

                db.commit()
                print("Database prepared for high-speed inserts")
            except Exception as e:
                db.rollback()
                print(f"Error preparing database: {e}")

    def restore_database(self):
        """Restore database constraints and rebuild indexes after data loading."""
        with self.get_session() as db:
            print("Restoring database constraints and indexes...")
            try:
                # Start transaction
                db.execute(text("BEGIN"))

                # Re-enable triggers
                db.execute(text("SET session_replication_role = 'origin'"))

                # Recreate any indexes that were dropped (if any)
                # db.execute(text("CREATE INDEX IF NOT EXISTS idx_function_name ON function(name)"))
                # Add more index creations here if needed

                db.commit()
                print("Starting VACUUM ANALYZE for better query planning...")
                db.execute(text("VACUUM ANALYZE"))
                print("Database constraints and indexes restored")
            except Exception as e:
                db.rollback()
                print(f"Error restoring database: {e}")

    def close_all_csv_files(self):
        """Close all open CSV files."""
        for table_info in self.csv_files.values():
            if table_info["file"] and not table_info["file"].closed:
                table_info["file"].close()

    def prepare_module_csv(self, module_list):
        """Prepare CSV file for modules."""
        print("Preparing modules CSV...")
        module_writer = self.prepare_csv_file("module", ["name", "path"])

        module_id = 1
        for module_name in module_list:
            module_path = self.function_parser.module_name_path.get(
                module_name, module_name
            )
            module_writer.writerow([module_name, module_path])
            self.module_id_map[module_name] = module_id
            module_id += 1

        print(f"Prepared {module_id-1} modules for bulk loading")

    def prepare_function_csv(self, functions_by_module):
        """Prepare CSV files for functions and where_functions."""
        print("Preparing functions CSV...")
        function_writer = self.prepare_csv_file(
            "function",
            [
                "id",
                "name",
                "function_signature",
                "raw_string",
                "src_loc",
                "line_number_start",
                "line_number_end",
                "type_enum",
                "module_id",
                "function_input",
                "function_output",
            ],
        )

        where_function_writer = self.prepare_csv_file(
            "where_function",
            [
                "id",
                "name",
                "function_signature",
                "raw_string",
                "src_loc",
                "parent_function_id",
            ],
        )

        function_dependency_writer = self.prepare_csv_file(
            "function_dependency", ["caller_id", "callee_id"]
        )

        function_id = 1
        where_function_id = 1
        dependency_count = 0

        # First pass - create all functions
        for module_name, functions in functions_by_module.items():
            module_id = self.module_id_map.get(module_name)
            if not module_id:
                continue

            for function in functions:
                # Handle JSON serialization
                function_input_json = (
                    json.dumps(function.function_input)
                    if function.function_input
                    else None
                )
                function_output_json = (
                    json.dumps(function.function_output)
                    if function.function_output
                    else None
                )

                # Write function data
                function_writer.writerow(
                    [
                        function_id,
                        function.function_name,
                        function.function_signature,
                        function.raw_string,
                        function.src_loc,
                        function.line_number_start,
                        function.line_number_end,
                        function.type_enum,
                        module_id,
                        function_input_json,
                        function_output_json,
                    ]
                )

                self.function_id_map[(module_name, function.function_name)] = (
                    function_id
                )

                # Process where functions
                for where_name, where_func in function.where_functions.items():
                    where_function_writer.writerow(
                        [
                            where_function_id,
                            where_func.function_name,
                            where_func.function_signature,
                            where_func.raw_string,
                            where_func.src_loc,
                            function_id,
                        ]
                    )
                    where_function_id += 1

                function_id += 1

        # Second pass - create dependencies
        for module_name, functions in functions_by_module.items():
            for function in functions:
                caller_id = self.function_id_map.get(
                    (module_name, function.function_name)
                )
                if not caller_id:
                    continue

                for called_function in function.functions_called:
                    if called_function.module_name and called_function.function_name:
                        callee_id = self.function_id_map.get(
                            (called_function.module_name, called_function.function_name)
                        )
                        if callee_id:
                            function_dependency_writer.writerow([caller_id, callee_id])
                            dependency_count += 1

        print(
            f"Prepared {function_id-1} functions, {where_function_id-1} where functions, and {dependency_count} dependencies for bulk loading"
        )

    def prepare_class_csv(self, classes_by_module):
        """Prepare CSV file for classes."""
        print("Preparing classes CSV...")
        class_writer = self.prepare_csv_file(
            "class",
            [
                "id",
                "class_name",
                "class_definition",
                "src_location",
                "line_number_start",
                "line_number_end",
                "module_id",
            ],
        )

        class_id = 1
        for module_name, classes in classes_by_module.items():
            module_id = self.module_id_map.get(module_name)
            if not module_id:
                continue

            for class_obj in classes:
                class_writer.writerow(
                    [
                        class_id,
                        class_obj.class_name,
                        class_obj.class_definition,
                        class_obj.src_location,
                        class_obj.line_number_start,
                        class_obj.line_number_end,
                        module_id,
                    ]
                )

                self.class_id_map[(module_name, class_obj.class_name)] = class_id
                class_id += 1

        print(f"Prepared {class_id-1} classes for bulk loading")

    def prepare_import_csv(self, imports_by_module):
        """Prepare CSV file for imports."""
        print("Preparing imports CSV...")
        import_writer = self.prepare_csv_file(
            "import",
            [
                "id",
                "module_name",
                "package_name",
                "src_loc",
                "is_boot_source",
                "is_safe",
                "is_implicit",
                "as_module_name",
                "qualified_style",
                "is_hiding",
                "hiding_specs",
                "line_number_start",
                "line_number_end",
                "module_id",
            ],
        )

        import_id = 1
        for module_name, imports in imports_by_module.items():
            module_id = self.module_id_map.get(module_name)
            if not module_id:
                continue

            for import_obj in imports:
                hiding_specs_json = (
                    json.dumps(import_obj.hiding_specs)
                    if import_obj.hiding_specs
                    else None
                )

                import_writer.writerow(
                    [
                        import_id,
                        import_obj.module_name,
                        import_obj.package_name,
                        import_obj.src_loc,
                        import_obj.is_boot_source,
                        import_obj.is_safe,
                        import_obj.is_implicit,
                        import_obj.as_module_name,
                        import_obj.qualified_style,
                        import_obj.is_hiding,
                        hiding_specs_json,
                        import_obj.line_number_start,
                        import_obj.line_number_end,
                        module_id,
                    ]
                )

                import_id += 1

        print(f"Prepared {import_id-1} imports for bulk loading")

    def prepare_type_csv(self, types_by_module):
        """Prepare CSV files for types, constructors, and fields."""
        print("Preparing types CSV...")
        type_writer = self.prepare_csv_file(
            "type",
            [
                "id",
                "type_name",
                "raw_code",
                "src_loc",
                "type_of_type",
                "line_number_start",
                "line_number_end",
                "module_id",
            ],
        )

        constructor_writer = self.prepare_csv_file(
            "constructor", ["id", "name", "type_id"]
        )

        field_writer = self.prepare_csv_file(
            "field",
            [
                "id",
                "field_name",
                "field_type_raw",
                "field_type_structure",
                "constructor_id",
            ],
        )

        type_dependency_writer = self.prepare_csv_file(
            "type_dependency", ["dependent_id", "dependency_id"]
        )

        type_id = 1
        constructor_id = 1
        field_id = 1

        for module_name, types in types_by_module.items():
            module_id = self.module_id_map.get(module_name)
            if not module_id:
                continue

            for type_obj in types:
                type_writer.writerow(
                    [
                        type_id,
                        type_obj.type_name,
                        type_obj.raw_code,
                        type_obj.src_loc,
                        type_obj.type.value,
                        type_obj.line_number_start,
                        type_obj.line_number_end,
                        module_id,
                    ]
                )

                self.type_id_map[(module_name, type_obj.type_name)] = type_id

                # Process constructors and fields
                for cons_name, fields in type_obj.cons.items():
                    constructor_writer.writerow([constructor_id, cons_name, type_id])

                    self.constructor_id_map[
                        (module_name, type_obj.type_name, cons_name)
                    ] = constructor_id

                    # Process fields
                    for field in fields:
                        field_type_structure = None
                        if field.field_type.structure:
                            try:
                                field_type_structure = json.dumps(
                                    field.field_type.structure.model_dump()
                                )
                            except Exception as e:
                                print(f"Error serializing field type structure: {e}")

                        field_writer.writerow(
                            [
                                field_id,
                                field.field_name,
                                field.field_type.raw_code,
                                field_type_structure,
                                constructor_id,
                            ]
                        )

                        field_id += 1

                    constructor_id += 1

                type_id += 1

        print(
            f"Prepared {type_id-1} types, {constructor_id-1} constructors, and {field_id-1} fields for bulk loading"
        )

    def prepare_instance_csv(self, instances_by_module):
        """Prepare CSV files for instances and instance_function associations."""
        print("Preparing instances CSV...")
        instance_writer = self.prepare_csv_file(
            "instance",
            [
                "id",
                "instance_definition",
                "instance_signature",
                "src_loc",
                "line_number_start",
                "line_number_end",
                "module_id",
            ],
        )

        instance_function_writer = self.prepare_csv_file(
            "instance_function", ["id", "instance_id", "function_id"]
        )

        instance_id = 1
        instance_function_id = 1

        for module_name, instances in instances_by_module.items():
            module_id = self.module_id_map.get(module_name)
            if not module_id:
                continue

            for instance in instances:
                instance_writer.writerow(
                    [
                        instance_id,
                        instance.instanceDefinition,
                        instance.instance_signature,
                        instance.src_loc,
                        instance.line_number_start,
                        instance.line_number_end,
                        module_id,
                    ]
                )

                self.instance_id_map[(module_name, instance.instanceDefinition)] = (
                    instance_id
                )

                # Process instance-function associations
                for function in instance.functions:
                    function_id = self.function_id_map.get(
                        (module_name, function.function_name)
                    )
                    if function_id:
                        instance_function_writer.writerow(
                            [instance_function_id, instance_id, function_id]
                        )
                        instance_function_id += 1

                instance_id += 1

        print(
            f"Prepared {instance_id-1} instances and {instance_function_id-1} instance-function associations for bulk loading"
        )

    def execute_bulk_load(self):
        """Execute PostgreSQL COPY commands to load all CSV data into the database."""
        with self.get_session() as db:
            for table_name, table_info in self.csv_files.items():
                print(f"Loading data into {table_name}...")
                columns_str = ", ".join(table_info["columns"])
                copy_sql = f"""
                    COPY {table_name}({columns_str})
                    FROM '{table_info['path']}'
                    WITH (FORMAT csv, HEADER true, DELIMITER ',')
                """
                try:
                    tic = time.perf_counter()
                    db.execute(text(copy_sql))
                    db.commit()
                    toc = time.perf_counter()
                    print(f"Loaded {table_name} in {toc - tic:0.4f} seconds")
                except Exception as e:
                    db.rollback()
                    print(f"Error loading {table_name}: {e}")

    def insert_data(self) -> None:
        """Process all dump files and insert the data into the database."""
        try:
            # Create temporary directory for CSV files
            self.temp_dir = tempfile.mkdtemp()
            print(f"Using temporary directory for CSV files: {self.temp_dir}")

            # Process all data
            print("Processing functions...")
            tic = time.perf_counter()
            functions_by_module = self.process_functions()
            toc = time.perf_counter()
            print(f"Processing functions completed in {toc - tic:0.4f} seconds")

            print("Processing classes...")
            tic = time.perf_counter()
            classes_by_module = self.process_classes()
            toc = time.perf_counter()
            print(f"Processing classes completed in {toc - tic:0.4f} seconds")

            print("Processing imports...")
            tic = time.perf_counter()
            imports_by_module = self.process_imports()
            toc = time.perf_counter()
            print(f"Processing imports completed in {toc - tic:0.4f} seconds")

            print("Processing types...")
            tic = time.perf_counter()
            types_by_module = self.process_types()
            toc = time.perf_counter()
            print(f"Processing types completed in {toc - tic:0.4f} seconds")

            print("Processing instances...")
            tic = time.perf_counter()
            instances_by_module = self.process_instances(functions_by_module)
            toc = time.perf_counter()
            print(f"Processing instances completed in {toc - tic:0.4f} seconds")

            # Combine all modules into one list
            module_list = set(
                list(functions_by_module.keys())
                + list(classes_by_module.keys())
                + list(imports_by_module.keys())
                + list(types_by_module.keys())
                + list(instances_by_module.keys())
            )
            print(f"Total modules to process: {len(module_list)}")

            # Prepare database for high-speed inserts
            self.prepare_database()

            try:
                # Generate CSV files for all data
                print("Converting data to CSV files...")
                tic = time.perf_counter()

                self.prepare_module_csv(module_list)
                self.prepare_function_csv(functions_by_module)
                self.prepare_class_csv(classes_by_module)
                self.prepare_import_csv(imports_by_module)
                self.prepare_type_csv(types_by_module)
                self.prepare_instance_csv(instances_by_module)

                toc = time.perf_counter()
                print(f"CSV preparation completed in {toc - tic:0.4f} seconds")

                # Close all CSV files before bulk loading
                self.close_all_csv_files()

                # Bulk load all CSV files into the database
                print("Bulk loading data into database...")
                tic = time.perf_counter()
                self.execute_bulk_load()
                toc = time.perf_counter()
                print(f"Bulk loading completed in {toc - tic:0.4f} seconds")

            finally:
                # Restore database constraints
                self.restore_database()

            print("Data import completed successfully!")

        except Exception as e:
            print(f"Error during data processing and loading: {e}")
            raise
        finally:
            # Clean up temporary files
            if self.temp_dir:
                try:
                    shutil.rmtree(self.temp_dir)
                    print(f"Cleaned up temporary directory: {self.temp_dir}")
                except Exception as e:
                    print(f"Error cleaning up temporary directory: {e}")
