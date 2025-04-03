import json
from typing import Dict, List, Optional

from . import list_files_recursive, get_module_name, error_trace
from src.code_as_data.models.class_model import Class


class ClassParser:
    """Parser for class data from dump files."""

    def __init__(self, json_path: str):
        """
        Initialize the class parser.

        Args:
            json_path: Path to the class dump files
        """
        self.json_path = json_path
        self.classesPerModule: Dict[str, List[Class]] = {}

    def process_single_class_module(self, file_path: str) -> Optional[List[Class]]:
        """
        Process a single class module file.

        Args:
            file_path: Path to the class file

        Returns:
            List of Class objects if successful, None otherwise
        """
        try:
            module_name = get_module_name(
                base_dir_path=self.json_path,
                path=file_path,
                to_replace=".class_code.json",
            )

            with open(file_path, "r") as f:
                class_data = json.load(f)

            classes_list = []
            for class_item in class_data:
                class_obj = self._process_class_data(class_item, module_name)
                if class_obj:
                    classes_list.append(class_obj)

            if classes_list:
                self.classesPerModule[module_name] = classes_list
                return classes_list

            return None
        except Exception as e:
            error_trace(e)
            print(f"Error processing classes for module {file_path}: {e}")
            return None

    def _process_class_data(
        self, class_item: Dict, module_name: str
    ) -> Optional[Class]:
        """
        Process a single class item.

        Args:
            class_item: Class data to process
            module_name: Name of the module

        Returns:
            Class object if successful, None otherwise
        """
        try:
            return Class(
                class_name=class_item.get("className"),
                class_definition=class_item.get("classDefinition"),
                src_location=class_item.get("classLocation"),
                line_number_start=class_item.get("line_number", [-1, -1])[0],
                line_number_end=class_item.get("line_number", [-1, -1])[1],
                module_name=module_name,
            )
        except Exception as e:
            error_trace(e)
            print(f"Error processing class: {e}")
            return None

    def _get_module_files(self) -> List[str]:
        """
        Get all module class files in the path.

        Returns:
            List of file paths
        """
        files = list_files_recursive(self.json_path, pattern=".class_code.json")
        return files

    def load(self) -> Dict[str, List[Class]]:
        """
        Load all class information and update internal state.

        Returns:
            Dictionary of module names to their class lists
        """
        # Clear existing state
        self.classesPerModule = {}

        # Process each module file
        for file_path in self._get_module_files():
            self.process_single_class_module(file_path)

        return self.classesPerModule
