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

from code_as_data.db.connection import SessionLocal
from code_as_data.db.models import Module
from code_as_data.parsers.function_parser import FunctionParser
from code_as_data.parsers.class_parser import ClassParser
from code_as_data.parsers.import_parser import ImportParser
from code_as_data.parsers.type_parser import TypeParser
from code_as_data.parsers.instance_parser import InstanceParser
from code_as_data.models.function_model import Function
from code_as_data.models.class_model import Class
from code_as_data.models.import_model import Import
from code_as_data.models.type_model import Type
from code_as_data.models.instance_model import Instance
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

        # Initialize parsers
        self.function_parser = FunctionParser(fdep_path)
        self.class_parser = ClassParser(fdep_path)
        self.import_parser = ImportParser(fdep_path)
        self.type_parser = TypeParser(fdep_path)

        # For optimized bulk loading
        self.temp_dir = None
        self.module_id_map = {}
        self.function_id_map = {}
        self.where_function_id_map = {}
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

    def get_next_id(self, table_name, id_column="id"):
        """Get the next available ID for a table."""
        try:
            with self.get_session() as db:
                result = db.execute(
                    text(f"SELECT COALESCE(MAX({id_column}), 0) + 1 FROM {table_name}")
                ).scalar()
                return result or 1  # Return 1 if the result is None (empty table)
        except Exception as e:
            print(f"Error getting next ID for {table_name}: {e}")
            return 1  # Default to 1 if there's an error

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

                db.commit()
                print("Database prepared for high-speed inserts")
            except Exception as e:
                db.rollback()
                print(f"Error preparing database: {e}")

    def restore_database(self):
        """Restore database constraints and rebuild indexes after data loading."""
        # First handle the transaction-based operations
        with self.get_session() as db:
            print("Restoring database constraints and indexes...")
            try:
                # Start transaction
                db.execute(text("BEGIN"))

                # Re-enable triggers
                db.execute(text("SET session_replication_role = 'origin'"))

                db.commit()
                print("Database constraints and indexes restored")
            except Exception as e:
                db.rollback()
                print(f"Error restoring database constraints: {e}")

        # Now handle VACUUM ANALYZE, which must be outside a transaction
        try:
            # Create a new session specifically for VACUUM
            with self.get_session() as vacuum_db:
                print("Starting VACUUM ANALYZE for better query planning...")
                # Set autocommit to True to run outside a transaction
                vacuum_db.execute(text("COMMIT"))  # Ensure no transaction is active
                vacuum_db.connection().connection.set_isolation_level(
                    0
                )  # AUTOCOMMIT isolation level
                vacuum_db.execute(text("VACUUM ANALYZE"))
                print("VACUUM ANALYZE completed successfully")
        except Exception as e:
            print(f"Error during VACUUM ANALYZE: {e}")
            print("Continuing despite VACUUM error (this is not critical)")

    def close_all_csv_files(self):
        """Close all open CSV files."""
        for table_info in self.csv_files.values():
            if table_info["file"] and not table_info["file"].closed:
                table_info["file"].close()

    def prepare_module_csv(self, module_list):
        """Prepare CSV file for modules."""
        print("Preparing modules CSV...")
        module_writer = self.prepare_csv_file("module", ["id", "name", "path"])

        module_id = self.get_next_id("module")
        for module_name in module_list:
            module_path = self.function_parser.module_name_path.get(
                module_name, module_name
            )
            module_writer.writerow([module_id, module_name, module_path])
            self.module_id_map[module_name] = module_id
            module_id += 1

        print(f"Prepared {module_id-1} modules for bulk loading")

    def prepare_function_csv(self, functions_by_module):
        """Prepare CSV files for functions and where_functions with improved ID handling."""
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
                "module_name",
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

        # Use a set to track unique function dependencies
        function_dependencies = set()
        function_dependency_writer = self.prepare_csv_file(
            "function_dependency", ["caller_id", "callee_id"]
        )

        # First pass - create a more robust function ID mapping
        print("First pass: Generating robust function ID mappings...")

        # Dictionary to store all functions with their signatures for disambiguation
        all_functions = {}
        function_canonical_keys = {}

        for module_name, functions in functions_by_module.items():
            for function in functions:
                # Create a canonical key that includes more information to disambiguate
                canonical_signature = function.function_signature or ""

                if function.src_loc and function.line_number_start > 0:
                    canonical_key = f"{module_name}:{function.function_name}:{canonical_signature}:{function.src_loc}:{function.line_number_start}"
                else:
                    canonical_key = (
                        f"{module_name}:{function.function_name}:{canonical_signature}"
                    )

                # Store the function with its canonical key
                all_functions[canonical_key] = function

                # Map the simple key to this canonical key to use in dependency resolution
                simple_key = (module_name, function.function_name)

                if simple_key in function_canonical_keys:
                    # If we already have this simple key, make a list of canonical keys for it
                    if isinstance(function_canonical_keys[simple_key], list):
                        function_canonical_keys[simple_key].append(canonical_key)
                    else:
                        function_canonical_keys[simple_key] = [
                            function_canonical_keys[simple_key],
                            canonical_key,
                        ]
                else:
                    function_canonical_keys[simple_key] = canonical_key

        # Second pass - write function data with assigned IDs
        print("Second pass: Writing function data with assigned IDs...")
        function_id = self.get_next_id("function")
        where_function_id = self.get_next_id("where_function")

        # Mapping from canonical keys to function IDs
        canonical_key_to_id = {}

        for canonical_key, function in all_functions.items():
            module_name = function.module_name
            module_id = self.module_id_map.get(module_name)
            if not module_id:
                continue

            # Handle JSON serialization
            function_input_json = (
                json.dumps(function.function_input) if function.function_input else None
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
                    function.module_name,
                    function_input_json,
                    function_output_json,
                ]
            )

            # Store the ID for this canonical key
            canonical_key_to_id[canonical_key] = function_id

            # Process where functions
            for where_name, where_func in function.where_functions.items():
                # line_start = getattr(where_func, "line_number_start", None)
                # line_end = getattr(where_func, "line_number_end", None)

                where_function_writer.writerow(
                    [
                        where_function_id,
                        where_func.function_name,
                        getattr(where_func, "function_signature", None),
                        getattr(where_func, "raw_string", None),
                        getattr(where_func, "src_loc", None),
                        # line_start,
                        # line_end,
                        function_id,
                    ]
                )

                # Store where function ID for later use
                where_key = f"{module_name}:{function.function_name}:{where_name}"
                self.where_function_id_map[where_key] = where_function_id

                where_function_id += 1

            function_id += 1

        # Third pass - create dependencies using canonical keys for lookup
        print("Third pass: Creating function dependencies...")
        dependency_count = 0
        skipped_duplicates = 0
        missing_dependencies = 0
        ambiguous_dependencies = 0

        for module_name, functions in functions_by_module.items():
            for function in functions:
                # Get the canonical key(s) for the caller
                simple_caller_key = (module_name, function.function_name)
                caller_canonical_keys = function_canonical_keys.get(simple_caller_key)

                if not caller_canonical_keys:
                    continue

                # Handle both single and multiple canonical keys
                if not isinstance(caller_canonical_keys, list):
                    caller_canonical_keys = [caller_canonical_keys]

                for caller_canonical_key in caller_canonical_keys:
                    caller_id = canonical_key_to_id.get(caller_canonical_key)
                    if not caller_id:
                        continue

                    for called_function in function.functions_called:
                        if (
                            not called_function.module_name
                            or not called_function.function_name
                        ):
                            continue

                        # Get the canonical key(s) for the callee
                        simple_callee_key = (
                            called_function.module_name,
                            called_function.function_name,
                        )
                        callee_canonical_keys = function_canonical_keys.get(
                            simple_callee_key
                        )

                        if not callee_canonical_keys:
                            missing_dependencies += 1
                            continue

                        # Handle both single and multiple canonical keys
                        if not isinstance(callee_canonical_keys, list):
                            callee_canonical_keys = [callee_canonical_keys]

                        # If we have multiple canonical keys for the callee, we consider it ambiguous
                        if len(callee_canonical_keys) > 1:
                            ambiguous_dependencies += 1

                        for callee_canonical_key in callee_canonical_keys:
                            callee_id = canonical_key_to_id.get(callee_canonical_key)
                            if not callee_id:
                                continue

                            # Check if this is a duplicate dependency
                            dependency_key = (caller_id, callee_id)
                            if dependency_key not in function_dependencies:
                                function_dependencies.add(dependency_key)
                                function_dependency_writer.writerow(
                                    [caller_id, callee_id]
                                )
                                dependency_count += 1
                            else:
                                skipped_duplicates += 1

        # Update the function ID map for later use
        self.function_id_map = {
            simple_key: canonical_key_to_id[canonical_key]
            for simple_key, canonical_key in function_canonical_keys.items()
            if not isinstance(canonical_key, list)
            and canonical_key in canonical_key_to_id
        }

        print(
            f"Prepared {function_id-1} functions, {where_function_id-1} where functions"
        )
        print(
            f"Prepared {dependency_count} unique function dependencies (skipped {skipped_duplicates} duplicates)"
        )
        print(
            f"Could not resolve {missing_dependencies} dependencies due to missing functions"
        )
        print(f"Encountered {ambiguous_dependencies} ambiguous dependencies")

    def prepare_function_called_csv(self, functions_by_module):
        """Prepare CSV file for function_called entities."""
        print("Preparing function_called CSV...")
        function_called_writer = self.prepare_csv_file(
            "function_called",
            [
                "id",
                "module_name",
                "name",
                "function_name",
                "package_name",
                "src_loc",
                "_type",
                "function_signature",
                "type_enum",
                "function_id",
                "where_function_id",
            ],
        )

        function_called_id = self.get_next_id("function_called")
        function_call_count = 0

        # Process all functions and their calls
        for module_name, functions in functions_by_module.items():
            for function in functions:
                # Get the function_id for this function
                function_id = self.function_id_map.get(
                    (module_name, function.function_name)
                )
                if not function_id:
                    continue

                # Process function calls from this function
                if hasattr(function, "functions_called") and function.functions_called:
                    for called_function in function.functions_called:
                        # Extract attributes from the called function
                        module_name_val = getattr(called_function, "module_name", None)
                        name_val = getattr(called_function, "name", None)
                        function_name_val = (
                            getattr(called_function, "function_name", None) or name_val
                        )
                        package_name_val = getattr(
                            called_function, "package_name", None
                        )
                        src_loc_val = getattr(called_function, "src_loc", None)
                        type_val = getattr(called_function, "_type", None) or getattr(
                            called_function, "type_enum", ""
                        )
                        function_signature_val = getattr(
                            called_function, "function_signature", None
                        )
                        type_enum_val = getattr(
                            called_function, "type_enum", None
                        ) or getattr(called_function, "_type", "")

                        # Write to CSV
                        function_called_writer.writerow(
                            [
                                function_called_id,
                                module_name_val,
                                name_val,
                                function_name_val,
                                package_name_val,
                                src_loc_val,
                                type_val,
                                function_signature_val,
                                type_enum_val,
                                function_id,
                                None,  # where_function_id is None here
                            ]
                        )

                        function_called_id += 1
                        function_call_count += 1

                # Process where functions and their calls
                for where_name, where_func in function.where_functions.items():
                    # Use the where function ID from our mapping
                    where_key = f"{module_name}:{function.function_name}:{where_name}"
                    where_function_id = self.where_function_id_map.get(where_key)

                    if not where_function_id:
                        continue

                    # Process function calls from this where function
                    if (
                        hasattr(where_func, "functions_called")
                        and where_func.functions_called
                    ):
                        for called_function in where_func.functions_called:
                            # Extract attributes from the called function
                            module_name_val = getattr(
                                called_function, "module_name", None
                            )
                            name_val = getattr(called_function, "name", None)
                            function_name_val = (
                                getattr(called_function, "function_name", None)
                                or name_val
                            )
                            package_name_val = getattr(
                                called_function, "package_name", None
                            )
                            src_loc_val = getattr(called_function, "src_loc", None)
                            type_val = getattr(
                                called_function, "_type", None
                            ) or getattr(called_function, "type_enum", "")
                            function_signature_val = getattr(
                                called_function, "function_signature", None
                            )
                            type_enum_val = getattr(
                                called_function, "type_enum", None
                            ) or getattr(called_function, "_type", "")

                            # Write to CSV
                            function_called_writer.writerow(
                                [
                                    function_called_id,
                                    module_name_val,
                                    name_val,
                                    function_name_val,
                                    package_name_val,
                                    src_loc_val,
                                    type_val,
                                    function_signature_val,
                                    type_enum_val,
                                    None,  # function_id is None for where function calls
                                    where_function_id,
                                ]
                            )

                            function_called_id += 1
                            function_call_count += 1

        print(f"Prepared {function_call_count} function calls for bulk loading")
        return function_call_count

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

        class_id = self.get_next_id("class")
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

        import_id = self.get_next_id("import")
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

        type_id = self.get_next_id("type")
        constructor_id = self.get_next_id("constructor")
        field_id = self.get_next_id("field")

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

        instance_id = self.get_next_id("instance")
        instance_function_id = self.get_next_id("instance_function")

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

        # Load in this specific order to handle dependencies properly
        table_order = [
            "module",
            "function",
            "where_function",
            "function_called",
            "class",
            "import",
            "type",
            "constructor",
            "field",
            "instance",
            "instance_function",
            "function_dependency",
            "type_dependency",
        ]

        # Define column types for tables that need special handling
        column_types = {
            "function_dependency": {"caller_id": "INTEGER", "callee_id": "INTEGER"},
            "type_dependency": {"dependent_id": "INTEGER", "dependency_id": "INTEGER"},
        }

        with self.get_session() as db:
            for table_name in table_order:
                if table_name not in self.csv_files:
                    continue

                table_info = self.csv_files[table_name]
                print(f"Loading data into {table_name}...")
                columns_str = ", ".join(table_info["columns"])

                # Special handling for tables with potential duplicates
                if table_name in ["function_dependency", "type_dependency"]:
                    try:
                        # Create type definitions string for temp table
                        type_defs = []
                        for col in table_info["columns"]:
                            col_type = column_types.get(table_name, {}).get(col, "TEXT")
                            type_defs.append(f"{col} {col_type}")

                        # Try using a temp table with proper column types
                        temp_table_name = f"temp_{table_name}"
                        copy_sql = f"""
                            CREATE TEMP TABLE {temp_table_name} (
                                {', '.join(type_defs)}
                            );
                            
                            COPY {temp_table_name}({columns_str})
                            FROM '{table_info['path']}'
                            WITH (FORMAT csv, HEADER true, DELIMITER ',');
                            
                            INSERT INTO {table_name} ({columns_str})
                            SELECT {columns_str} FROM {temp_table_name}
                            ON CONFLICT DO NOTHING;
                            
                            DROP TABLE {temp_table_name};
                        """
                        tic = time.perf_counter()
                        db.execute(text(copy_sql))
                        db.commit()
                        toc = time.perf_counter()
                        print(
                            f"Loaded {table_name} (with duplicate handling) in {toc - tic:0.4f} seconds"
                        )
                    except Exception as e:
                        db.rollback()
                        print(
                            f"Error loading {table_name} with duplicate handling: {e}"
                        )

                        # Fallback to direct COPY with a pre-cleanup step
                        try:
                            # First create a clean CSV without duplicates
                            clean_csv_path = self.create_clean_csv(
                                table_name, table_info["path"]
                            )

                            # Use COPY for the cleaned CSV
                            copy_sql = f"""
                                COPY {table_name}({columns_str})
                                FROM '{clean_csv_path}'
                                WITH (FORMAT csv, HEADER true, DELIMITER ',')
                            """
                            db.execute(text(copy_sql))
                            db.commit()
                            print(f"Loaded {table_name} using cleaned CSV")
                        except Exception as e2:
                            db.rollback()
                            print(f"Failed alternative loading for {table_name}: {e2}")

                            # Last resort: manual insert for this table
                            print(f"Falling back to manual insert for {table_name}")
                            self.manual_load_with_duplicate_checking(
                                db, table_name, table_info["path"]
                            )

                else:
                    # Standard COPY for tables without duplicate concerns
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

    def manual_load_with_duplicate_checking(self, db, table_name, csv_path):
        """Manual row-by-row loading with duplicate checking as a last resort."""
        try:
            with open(csv_path, "r") as csvfile:
                csv_reader = csv.reader(csvfile)
                next(csv_reader)  # Skip header

                loaded = 0
                skipped = 0
                batch = []
                batch_size = 1000

                for row in csv_reader:
                    if table_name == "function_dependency":
                        caller_id, callee_id = row

                        # Check if this dependency already exists
                        result = db.execute(
                            text(
                                f"SELECT 1 FROM {table_name} WHERE caller_id = :caller_id AND callee_id = :callee_id"
                            ),
                            {"caller_id": int(caller_id), "callee_id": int(callee_id)},
                        ).fetchone()

                        if not result:
                            batch.append((int(caller_id), int(callee_id)))
                            loaded += 1

                            # Insert in batches for better performance
                            if len(batch) >= batch_size:
                                self.insert_dependency_batch(db, table_name, batch)
                                batch = []
                        else:
                            skipped += 1

                    elif table_name == "type_dependency":
                        dependent_id, dependency_id = row

                        result = db.execute(
                            text(
                                f"SELECT 1 FROM {table_name} WHERE dependent_id = :dependent_id AND dependency_id = :dependency_id"
                            ),
                            {
                                "dependent_id": int(dependent_id),
                                "dependency_id": int(dependency_id),
                            },
                        ).fetchone()

                        if not result:
                            batch.append((int(dependent_id), int(dependency_id)))
                            loaded += 1

                            if len(batch) >= batch_size:
                                self.insert_dependency_batch(db, table_name, batch)
                                batch = []
                        else:
                            skipped += 1

                # Insert any remaining items
                if batch:
                    self.insert_dependency_batch(db, table_name, batch)

                print(
                    f"Manually loaded {loaded} rows into {table_name} (skipped {skipped} duplicates)"
                )

        except Exception as e:
            db.rollback()
            print(f"Error during manual loading of {table_name}: {e}")

    def extreme_parallel_processing(self):
        """
        Ultra-optimized parallel data processing implementation.

        This implementation:
        1. Uses a ProcessPoolExecutor for truly parallel execution on multiple cores
        2. Handles dependencies properly (instances depend on functions)
        3. Optimizes memory usage with prefetching and caching
        4. Uses shared memory where possible to reduce copying overhead
        5. Implements CPU affinity for critical processes

        Returns:
            Tuple of (functions_by_module, classes_by_module, imports_by_module,
                    types_by_module, instances_by_module)
        """
        import concurrent.futures
        import psutil
        import os

        # Detect system capabilities
        cpu_count = psutil.cpu_count(logical=False)  # Physical cores
        total_cores = psutil.cpu_count(
            logical=True
        )  # Logical cores (including hyperthreading)

        # Determine optimal number of workers
        max_workers = min(cpu_count, 4)  # Cap at 4 to avoid diminishing returns
        print(
            f"Starting extreme parallel processing with {max_workers} workers on {total_cores} cores..."
        )

        # Force garbage collection before starting
        import gc

        gc.collect()

        overall_start = time.perf_counter()

        # Pin current process to core 0 to avoid contention with worker processes
        try:
            current_process = psutil.Process(os.getpid())
            current_process.cpu_affinity([0])
            print("Main process pinned to CPU core 0")
        except Exception as e:
            print(f"Could not set CPU affinity: {e}")

        # First, process functions (needed for instances)
        # We'll do this in the main process to avoid serialization overhead
        print("Processing functions...")
        tic = time.perf_counter()
        self.function_parser.load_all_files()
        functions = self.function_parser.get_functions()

        # Pre-allocate dictionary with known size
        functions_by_module = {}
        for function in functions:
            if function.module_name not in functions_by_module:
                functions_by_module[function.module_name] = []
            functions_by_module[function.module_name].append(function)

        # Delete the full list to free memory
        del functions
        toc = time.perf_counter()
        print(
            f"Processing functions completed in {toc - tic:0.4f} seconds - {len(functions_by_module)} modules found"
        )

        # Force garbage collection again
        gc.collect()

        # Now process the rest in parallel
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=max_workers
        ) as executor:
            # Start the class parsing on another process
            print("Starting parallel class parsing...")
            future_classes = executor.submit(self.class_parser.load)

            # Start the import parsing
            print("Starting parallel import parsing...")
            future_imports = executor.submit(self.import_parser.load)

            # Start the type parsing
            print("Starting parallel type parsing...")
            future_types = executor.submit(self.type_parser.load)

            # Process instances in the main process while others are running
            # This depends on functions which we already have
            print("Processing instances (main process)...")
            tic = time.perf_counter()
            instance_parser = InstanceParser(
                self.fdep_path, self.fdep_path, functions_by_module
            )
            instances_by_module = instance_parser.load_all_files()
            toc = time.perf_counter()
            print(f"Processing instances completed in {toc - tic:0.4f} seconds")

            # Get results from futures
            # We'll get them in order of expected completion time to avoid blocking
            print("Waiting for parallel parsers to complete...")

            # Classes typically complete first
            tic = time.perf_counter()
            classes_by_module = future_classes.result()
            toc = time.perf_counter()
            print(f"Classes parsing completed in {toc - tic:0.4f} seconds")

            # Imports typically next
            tic = time.perf_counter()
            imports_by_module = future_imports.result()
            toc = time.perf_counter()
            print(f"Imports parsing completed in {toc - tic:0.4f} seconds")

            # Types typically last
            tic = time.perf_counter()
            types_by_module = future_types.result()
            toc = time.perf_counter()
            print(f"Types parsing completed in {toc - tic:0.4f} seconds")

        # Reset CPU affinity if needed
        try:
            current_process = psutil.Process(os.getpid())
            current_process.cpu_affinity(list(range(total_cores)))
            print("Main process CPU affinity reset")
        except Exception:
            pass  # Ignore errors here

        # Final garbage collection
        gc.collect()

        overall_end = time.perf_counter()
        print(
            f"All data processing completed in {overall_end - overall_start:0.4f} seconds (extreme parallel mode)"
        )

        return (
            functions_by_module,
            classes_by_module,
            imports_by_module,
            types_by_module,
            instances_by_module,
        )

    def insert_data(self) -> None:
        """Process all dump files and insert the data into the database."""
        try:
            # Create temporary directory for CSV files
            self.temp_dir = tempfile.mkdtemp()
            print(f"Using temporary directory for CSV files: {self.temp_dir}")

            # Process all data using extreme parallelization
            print("Starting extreme parallel data processing...")
            (
                functions_by_module,
                classes_by_module,
                imports_by_module,
                types_by_module,
                instances_by_module,
            ) = self.extreme_parallel_processing()

            # Rest of the method remains unchanged
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
                self.prepare_function_called_csv(functions_by_module)
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

    def create_clean_csv(self, table_name, original_csv_path):
        """Create a clean CSV file with no duplicates."""
        clean_csv_path = os.path.join(self.temp_dir, f"clean_{table_name}.csv")

        try:
            if table_name == "function_dependency":
                # Process function dependencies
                seen_keys = set()

                with open(original_csv_path, "r", newline="") as csv_in, open(
                    clean_csv_path, "w", newline=""
                ) as csv_out:

                    reader = csv.reader(csv_in)
                    writer = csv.writer(csv_out)

                    # Write header
                    header = next(reader)
                    writer.writerow(header)

                    # Process and filter rows
                    for row in reader:
                        key = (row[0], row[1])  # (caller_id, callee_id)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            writer.writerow(row)

                print(
                    f"Created clean CSV for {table_name} ({len(seen_keys)} unique entries)"
                )

            elif table_name == "type_dependency":
                # Process type dependencies (similar approach)
                seen_keys = set()

                with open(original_csv_path, "r", newline="") as csv_in, open(
                    clean_csv_path, "w", newline=""
                ) as csv_out:

                    reader = csv.reader(csv_in)
                    writer = csv.writer(csv_out)

                    # Write header
                    header = next(reader)
                    writer.writerow(header)

                    # Process and filter rows
                    for row in reader:
                        key = (row[0], row[1])  # (dependent_id, dependency_id)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            writer.writerow(row)

                print(
                    f"Created clean CSV for {table_name} ({len(seen_keys)} unique entries)"
                )

            return clean_csv_path

        except Exception as e:
            print(f"Error creating clean CSV for {table_name}: {e}")
            return original_csv_path  # Return original path if cleaning fails

    def insert_dependency_batch(self, db, table_name, batch):
        """Insert a batch of dependencies."""
        try:
            if table_name == "function_dependency":
                stmt = text(
                    f"""
                    INSERT INTO {table_name} (caller_id, callee_id)
                    VALUES (:caller_id, :callee_id)
                    ON CONFLICT DO NOTHING
                """
                )

                db.execute(
                    stmt,
                    [
                        {"caller_id": caller_id, "callee_id": callee_id}
                        for caller_id, callee_id in batch
                    ],
                )

            elif table_name == "type_dependency":
                stmt = text(
                    f"""
                    INSERT INTO {table_name} (dependent_id, dependency_id)
                    VALUES (:dependent_id, :dependency_id)
                    ON CONFLICT DO NOTHING
                """
                )

                db.execute(
                    stmt,
                    [
                        {"dependent_id": dependent_id, "dependency_id": dependency_id}
                        for dependent_id, dependency_id in batch
                    ],
                )

            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Error inserting batch into {table_name}: {e}")
