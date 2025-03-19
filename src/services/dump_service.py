from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

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


class DumpService:
    """Service for handling dump file processing and database insertion."""

    def __init__(self, db: Session, fdep_path: str, field_inspector_path: str):
        """
        Initialize the dump service.

        Args:
            db: Database session
            fdep_path: Path to the fdep files
            field_inspector_path: Path to the field inspector files
        """
        self.db = db
        self.fdep_path = fdep_path
        self.field_inspector_path = field_inspector_path
        self.repository = Repository(db)

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
        functions_by_module = self.process_functions()
        classes_by_module = self.process_classes()
        imports_by_module = self.process_imports()
        types_by_module = self.process_types()
        instances_by_module = self.process_instances(functions_by_module)

        # Store function IDs for later dependency linking
        function_ids = {}

        def process_for_module(module_name):
            # Create or get module
            module_path = self.function_parser.module_name_path.get(
                module_name, module_name
            )
            db_module = self.repository.get_or_create_module(module_name, module_path)

            # Insert functions
            for function in functions_by_module.get(module_name, []):
                db_function = self.repository.create_function(function, db_module.id)
                function_ids[(module_name, function.function_name)] = db_function.id

            # Insert classes
            for class_obj in classes_by_module.get(module_name, []):
                self.repository.create_class(class_obj, db_module.id)

            # Insert imports
            for import_obj in imports_by_module.get(module_name, []):
                self.repository.create_import(import_obj, db_module.id)

            # Insert types
            for type_obj in types_by_module.get(module_name, []):
                self.repository.create_type(type_obj, db_module.id)

            # Insert instances
            for instance in instances_by_module.get(module_name, []):
                self.repository.create_instance(instance, db_module.id)

        module_list = set(
            list(functions_by_module.keys())
            + list(classes_by_module.keys())
            + list(imports_by_module.keys())
            + list(types_by_module.keys())
            + list(instances_by_module.keys())
        )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future_to_file = {
                executor.submit(process_for_module, module): module
                for module in module_list
            }
            for future in concurrent.futures.as_completed(future_to_file):
                module = future_to_file[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Error reading {module}: {e}")

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
