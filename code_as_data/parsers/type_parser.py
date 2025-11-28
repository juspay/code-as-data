import json
import os
from typing import Dict, List, Optional, Any

from . import list_files_recursive, get_module_name, error_trace
from code_as_data.models.type_model import (
    Type,
    TypeField,
    StructuredTypeRep,
    ComplexType,
    TypeOfType,
)


class TypeParser:
    """Parser for type data from dump files."""

    def __init__(self, raw_code_path: str):
        """
        Initialize the type parser.

        Args:
            raw_code_path: Base path for raw code
            json_path: Path to the type dump files
        """
        self.raw_code_path = raw_code_path
        self.json_path = raw_code_path
        self.typesPerModule: Dict[str, List[Type]] = {}
        self.raw_code_cache: Dict[str, Dict[str, Dict[str, str]]] = {}

    def _load_raw_code_file(self, file_path: str) -> Dict[str, Dict[str, str]]:
        """
        Load and process a single raw code type file.

        Args:
            file_path: Path to the raw code file

        Returns:
            Dictionary of type name to type data
        """
        types = {}
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                for type_info in data:
                    types[type_info.get("typeName")] = {
                        "src_loc": type_info.get("typeLocation"),
                        "raw_code": type_info.get("typeDefinition"),
                        "line_number_start": type_info.get("line_number", [-1, -1])[0],
                        "line_number_end": type_info.get("line_number", [-1, -1])[1],
                    }
            return types
        except Exception as e:
            error_trace(e)
            print(f"Error loading raw code file {file_path}: {e}")
            return {}

    def _load_type_file(
        self, file_path: str, raw_code: Dict[str, Dict[str, Any]]
    ) -> List[Type]:
        """
        Load and process a single type JSON file.

        Args:
            file_path: Path to the type file
            raw_code: Dictionary of type raw code data

        Returns:
            List of Type objects
        """
        types = []
        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            module_name = get_module_name(
                base_dir_path=self.json_path,
                path=file_path,
                to_replace=".hs.type.typechecker.json",
            )

            for (key,value) in data.items():
                # Get raw code data
                raw_code_data = raw_code.get(key, {})

                # Create type data dictionary
                type_data = {
                    "type_name": key,
                    "module_name": module_name,
                    "data_constructors_list": value.get("dataConstructors", []),
                    "typeKind": value.get("typeKind"),
                    "src_loc": raw_code_data.get("src_loc", ""),
                    "raw_code": raw_code_data.get("raw_code", ""),
                    "line_number_start": raw_code_data.get("line_number_start", -1),
                    "line_number_end": raw_code_data.get("line_number_end", -1),
                }

                # Create Type object
                type_obj = Type(**type_data)
                types.append(type_obj)

            return types
        except Exception as e:
            error_trace(e)
            print(f"Error loading type file {file_path}: {e}")
            return []

    def process_single_module(self, type_file_path: str) -> Optional[List[Type]]:
        """
        Process a single module's type files.

        Args:
            type_file_path: Path to the type file

        Returns:
            List of Type objects if successful, None otherwise
        """
        try:
            # Get module name
            module_name = get_module_name(
                base_dir_path=self.json_path,
                path=type_file_path,
                to_replace=".hs.types.parser.json",
            )

            # Find and load corresponding raw code file
            raw_code_path = type_file_path.replace(
                self.json_path, self.raw_code_path
            ).replace(".types.parser.json", ".types_code.json")

            # Load raw code if it exists
            if os.path.exists(raw_code_path):
                raw_code = self._load_raw_code_file(raw_code_path)
                self.raw_code_cache[module_name] = raw_code
            else:
                raw_code = self.raw_code_cache.get(module_name, {})

            # Process types
            types = self._load_type_file(type_file_path, raw_code)

            # Update internal state
            if types:
                self.typesPerModule[module_name] = types
                return types

            return None

        except Exception as e:
            error_trace(e)
            print(f"Error processing type module {type_file_path}: {e}")
            return None

    def load(self) -> Dict[str, List[Type]]:
        """
        Load all type files and update internal state.

        Returns:
            Dictionary of module names to their type lists
        """
        # Clear existing state
        self.typesPerModule = {}
        self.raw_code_cache = {}

        # Find and load all raw code files
        typesRawCodeList = list_files_recursive(
            self.raw_code_path, pattern="hs.types_code.json"
        )

        # Process raw code files
        for file_path in typesRawCodeList:
            module_name = get_module_name(
                base_dir_path=self.raw_code_path,
                path=file_path,
                to_replace=".hs.types_code.json",
            )
            self.raw_code_cache[module_name] = self._load_raw_code_file(file_path)

        # Find and process all type files
        typesJSONList = list_files_recursive(
            self.json_path, pattern="hs.type.typechecker.json"
        )

        for file_path in typesJSONList:
            module_name = get_module_name(
                base_dir_path=self.json_path,
                path=file_path,
                to_replace=".hs.type.typechecker.json",
            )
            raw_code = self.raw_code_cache.get(module_name, {})
            types = self._load_type_file(file_path, raw_code)
            if types:
                self.typesPerModule[module_name] = types
        # ---- Rust FileAnalysis JSONs
        rust_jsons = [
            f for f in list_files_recursive(self.json_path, pattern=".json")
            if not f.endswith(".hs.json")
            and not f.endswith(".hs.type.typechecker.json")
            and not f.endswith(".hs.types_code.json")
            and not f.endswith(".hs.module_imports.json")
        ]
        for file_path in rust_jsons:
            try:
                with open(file_path, "r") as f:
                    obj = json.load(f)
            except Exception:
                continue

            # Only handle Rust FileAnalysis that actually has type_definitions
            if not isinstance(obj, dict) or "type_definitions" not in obj:
                continue

            def _infer_mod(o: Dict[str, Any]) -> str:
                for bucket in ("type_definitions", "functions", "impl_blocks",
                               "use_statements", "trait_method_signatures",
                               "constant_definitions", "module_declarations"):
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

            rows: List[Type] = []
            for t in obj.get("type_definitions", []) or []:
                try:
                    rows.append(Type(
                        type_name=t.get("name"),
                        module_name=module_name,
                        raw_code=t.get("src_code", ""),
                        src_loc=t.get("src_location", file_src),
                        line_number_start=t.get("line_number_start", -1),
                        line_number_end=t.get("line_number_end", -1),
                        fully_qualified_path=t.get("fully_qualified_path"),
                        fields=t.get("fields"),
                        visibility=t.get("visibility"),
                        doc_comments=t.get("doc_comments"),
                        attributes=t.get("attributes"),
                        crate_name=t.get("crate_name"),
                        module_path=t.get("module_path"),
                        type=TypeOfType.resolve_value(
                            t.get("type_kind", t.get("typeKind", "data"))
                        ),
                    ))
                except Exception as e:
                    error_trace(e)
                    continue

            if rows:
                self.typesPerModule.setdefault(module_name, []).extend(rows)

        return self.typesPerModule
