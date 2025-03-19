from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Dict, List, Optional
import time
from sqlalchemy.orm import Session

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
            db: Database session
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

    def insert_data(self) -> None:
        """Process all dump files and insert the data into the database."""
        # Process all data

        tic = time.perf_counter()
        functions_by_module = self.process_functions()
        toc = time.perf_counter()
        print(f"processing functions completed in {toc - tic:0.4f} seconds")

        tic = time.perf_counter()
        classes_by_module = self.process_classes()
        toc = time.perf_counter()
        print(f"processing classes completed in {toc - tic:0.4f} seconds")

        tic = time.perf_counter()
        imports_by_module = self.process_imports()
        toc = time.perf_counter()
        print(f"processing imports completed in {toc - tic:0.4f} seconds")

        tic = time.perf_counter()
        types_by_module = self.process_types()
        toc = time.perf_counter()
        print(f"processing types completed in {toc - tic:0.4f} seconds")

        tic = time.perf_counter()
        instances_by_module = self.process_instances(functions_by_module)
        toc = time.perf_counter()
        print(f"processing instances completed in {toc - tic:0.4f} seconds")

        # Store function IDs for later dependency linking
        function_ids = {}

        def get_session():
            """
            Tries to create a new session with retry logic and timeout handling.
            """
            attempt = 0
            while attempt < MAX_RETRIES:
                try:
                    # Try to create a session
                    session = SessionLocal()
                    return session
                except Exception as e:
                    print(
                        f"Attempt {attempt + 1}/{MAX_RETRIES} failed to create session: {e}"
                    )
                    attempt += 1
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)  # Wait before retrying
                    else:
                        print("Max retries reached, unable to create session.")
                        raise e  # Raise the last exception if retries are exhausted

        def process_for_module(module_name):
            db = get_session()
            print("processing module: ", module_name)
            tic = time.perf_counter()
            # Create or get module
            module_path = self.function_parser.module_name_path.get(
                module_name, module_name
            )
            db_module = self.repository.get_or_create_module(
                db, module_name, module_path
            )

            # Insert functions
            for function in functions_by_module.get(module_name, []):
                db_function = self.repository.create_function(
                    db, function, db_module.id
                )
                function_ids[(module_name, function.function_name)] = db_function.id

            # Insert classes
            for class_obj in classes_by_module.get(module_name, []):
                self.repository.create_class(db, class_obj, db_module.id)

            # Insert imports
            for import_obj in imports_by_module.get(module_name, []):
                self.repository.create_import(db, import_obj, db_module.id)

            # Insert types
            for type_obj in types_by_module.get(module_name, []):
                self.repository.create_type(db, type_obj, db_module.id)

            # Insert instances
            for instance in instances_by_module.get(module_name, []):
                self.repository.create_instance(db, instance, db_module.id)
            db.commit()
            db.close()

            toc = time.perf_counter()
            print(f"processed module {module_name} in {toc - tic:0.4f} seconds")

        module_list = set(
            list(functions_by_module.keys())
            + list(classes_by_module.keys())
            + list(imports_by_module.keys())
            + list(types_by_module.keys())
            + list(instances_by_module.keys())
        )
        print(len(module_list))
        cnt = 0
        with ThreadPoolExecutor(max_workers=250) as executor:
            future_to_file = {}
            for module in module_list:
                future = executor.submit(process_for_module, module)
                future_to_file[future] = module
            # future_to_file = {
            #     executor.submit(process_for_module, (db,module)): module
            #     for module in module_list
            # }
            for future in concurrent.futures.as_completed(future_to_file):
                module = future_to_file[future]
                try:
                    future.result()
                    cnt += 1
                    print(f"{cnt}/{len(module_list)}")
                except Exception as e:
                    print(f"insert_data: Error reading {module}: {e}")

            # Create function dependencies
        for module_name, functions in functions_by_module.items():
            for function in functions:
                caller_id = function_ids.get((module_name, function.function_name))
                if caller_id:
                    for called_function in function.functions_called:
                        if (
                            called_function.module_name
                            and called_function.function_name
                        ):
                            callee_id = function_ids.get(
                                (
                                    called_function.module_name,
                                    called_function.function_name,
                                )
                            )
                            if callee_id:
                                self.repository.create_function_dependency(
                                    caller_id, callee_id
                                )
