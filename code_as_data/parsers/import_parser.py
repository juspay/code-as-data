import json
from typing import Dict, List, Optional, Any

from . import list_files_recursive, get_module_name, error_trace
from code_as_data.models.import_model import Import


class ImportParser:
    """Parser for import data from dump files."""

    def __init__(self, raw_code_path: str):
        """
        Initialize the import parser.

        Args:
            raw_code_path: Base path for raw code
            path: Path to the import dump files
        """
        self.raw_code_path = raw_code_path
        self.path = raw_code_path
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

        # Process each Haskell module file
        for file_path in self._get_module_files():
            self.process_single_module(file_path)
        # ---- Rust FileAnalysis JSONs (minimal addition) ----
        rust_jsons = [
            f for f in list_files_recursive(self.path, pattern=".json")
            if not f.endswith(".hs.module_imports.json") and not f.endswith(".hs.json")
        ]
        for file_path in rust_jsons:
            try:
                with open(file_path, "r") as f:
                    obj = json.load(f)
            except Exception:
                continue

            # skip non-FileAnalysis or files without Rust use-statements
            if not isinstance(obj, dict) or "use_statements" not in obj:
                continue

            def _infer_mod(o: Dict[str, Any]) -> str:
                # Try to build "<crate>::<module_path>" from any bucket; fallback to unknown
                for bucket in ("use_statements","functions","type_definitions","impl_blocks",
                               "trait_method_signatures","constant_definitions","module_declarations"):
                    for it in o.get(bucket, []) or []:
                        crate = it.get("crate_name")
                        modp  = it.get("module_path") or ""
                        if crate:
                            return f"{crate}{('::' + modp) if modp else ''}"
                        fqp = it.get("fully_qualified_path")
                        if fqp:
                            return fqp.rsplit("::", 1)[0] if "::" in fqp else fqp
                return "<unknown_crate>"

            module_name = _infer_mod(obj)
            file_src    = obj.get("file_path", file_path)

            rows: List[Import] = []
            for u in obj.get("use_statements", []) or []:
                ln = u.get("line_number", -1)
                try:
                    rows.append(Import(
                        src_loc=file_src,
                        module_name=module_name,
                        line_number_start=ln,
                        line_number_end=ln,
                        path=u.get("path"),
                        visibility=u.get("visibility"),
                    ))
                except Exception as e:
                    error_trace(e)
                    continue
            if rows:
                self.imports.setdefault(module_name, []).extend(rows)

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
