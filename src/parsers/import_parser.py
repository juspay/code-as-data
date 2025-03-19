import json
from typing import Dict, List, Optional

from . import list_files_recursive, get_module_name, error_trace
from src.models.import_model import Import


class ImportParser:
    """Parser for import data from dump files."""

    def __init__(self, raw_code_path: str, path: str):
        """
        Initialize the import parser.

        Args:
            raw_code_path: Base path for raw code
            path: Path to the import dump files
        """
        self.raw_code_path = raw_code_path
        self.path = path
        self.imports: Dict[str, List[Import]] = {}

    def _process_import_data(
        self, import_item: Dict, file_path: str
    ) -> Optional[Import]:
        """
        Process a single import item.

        Args:
            import_item: Import data to process
            file_path: Path to the file

        Returns:
            Import object if successful, None otherwise
        """
        try:
            return Import(
                **{
                    "src_loc": file_path,
                    "moduleName'": import_item.get("moduleName'"),
                    "packageName": import_item.get("packageName"),
                    "asModuleName": import_item.get("asModuleName"),
                    "isImplicit": import_item.get("isImplicit"),
                    "isSafe": import_item.get("isSafe"),
                    "hidingSpec": import_item.get("hidingSpec"),
                    "qualifiedStyle": import_item.get("qualifiedStyle", {}),
                    "line_number_start": import_item.get("line_number", [-1, -1])[0],
                    "line_number_end": import_item.get("line_number", [-1, -1])[1],
                }
            )
        except Exception as e:
            error_trace(e)
            print(f"Error processing import: {e}")
            return None

    def process_single_module(self, file_path: str) -> Optional[List[Import]]:
        """
        Process a single module's imports.

        Args:
            file_path: Path to the module imports file

        Returns:
            List of Import objects if successful, None otherwise
        """
        try:
            # Extract module name
            module_name = get_module_name(
                base_dir_path=self.raw_code_path,
                path=file_path,
                to_replace=".hs.module_imports.json",
            )

            # Read and process file
            with open(file_path, "r") as f:
                import_data = json.load(f)

            # Process imports
            imports_list = []
            for import_item in import_data:
                import_obj = self._process_import_data(
                    import_item, file_path.replace(".module_imports.json", "")
                )
                if import_obj:
                    imports_list.append(import_obj)

            # Update internal state
            if imports_list:
                self.imports[module_name] = imports_list
                return imports_list

            return None

        except Exception as e:
            error_trace(e)
            print(f"Error processing imports for module {file_path}: {e}")
            return None

    def _get_module_files(self) -> List[str]:
        """
        Get all module import files in the path.

        Returns:
            List of file paths
        """
        return list_files_recursive(self.path, pattern=".module_imports.json")

    def load(self) -> Dict[str, List[Import]]:
        """
        Load all import information and update internal state.

        Returns:
            Dictionary of module names to their import lists
        """
        # Clear existing state
        self.imports = {}

        # Process each module file
        for file_path in self._get_module_files():
            self.process_single_module(file_path)

        return self.imports

    def get_imports_for_module(self, module_name: str) -> Optional[List[Import]]:
        """
        Get imports for a specific module.

        Args:
            module_name: Name of the module

        Returns:
            List of imports for the module if found, None otherwise
        """
        return self.imports.get(module_name)
