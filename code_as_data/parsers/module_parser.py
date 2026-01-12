# code_as_data/parsers/module_parser.py
import json
from typing import Dict, List, Optional, Any

from . import list_files_recursive, error_trace
from code_as_data.models.module_model import Module


class ModuleParser:
    """Parser for Rust module declarations from FileAnalysis JSON dumps."""

    def __init__(self, json_path: str):
        """
        Initialize the module parser.

        Args:
            json_path: Path to the Rust FileAnalysis JSON files
        """
        self.json_path = json_path
        self.modulesPerName: Dict[str, List[Module]] = {}

    # ---------- per-file processing ----------

    def process_single_module_file(self, file_path: str) -> Optional[List[Module]]:
        """
        Process a single Rust FileAnalysis JSON and collect module declarations.

        Args:
            file_path: Path to the FileAnalysis JSON

        Returns:
            List of Module objects if successful, None otherwise
        """
        try:
            with open(file_path, "r") as f:
                try:
                    obj = json.load(f)
                except json.JSONDecodeError:
                    return None  # Ignore empty or invalid JSON files

            # Only handle Rust FileAnalysis-shaped JSONs
            if not isinstance(obj, dict):
                return None

            file_src = obj.get("file_path", file_path)

            # If there are explicit module declarations, use them
            decls = obj.get("module_declarations", []) or []
            rows: List[Module] = []

            for md in decls:
                name_fqp = md.get("fully_qualified_path") or self._infer_fqp_from_any(md)
                name = name_fqp or self._infer_fqp_from_any(obj) or "<unknown_crate>"

                attrs_raw = md.get("attributes")
                attributes = (
                    [{"raw": a} for a in attrs_raw] if isinstance(attrs_raw, list) else None
                )

                try:
                    row = Module(
                        name=name,
                        path=file_src,
                        fully_qualified_path=name_fqp,
                        crate_name=md.get("crate_name"),
                        module_path=md.get("module_path"),
                        visibility=md.get("visibility"),
                        doc_comments=md.get("doc_comments"),
                        attributes=attributes,
                        line_number=md.get("line_number"),
                    )
                    rows.append(row)
                except Exception as e:
                    error_trace(e)
                    continue

            # If no declarations were found, synthesize a single module for the file
            if not rows:
                name = self._infer_fqp_from_any(obj) or "<unknown_crate>"
                try:
                    rows = [
                        Module(
                            name=name,
                            path=file_src,
                            fully_qualified_path=name,
                            crate_name=self._infer_crate(obj),
                            module_path=self._infer_module_path(obj),
                        )
                    ]
                except Exception as e:
                    error_trace(e)
                    rows = []

            if rows:
                # Key by module name (FQP), store possibly multiple per file
                for m in rows:
                    self.modulesPerName.setdefault(m.name, []).append(m)
                return rows

            return None

        except Exception as e:
            error_trace(e)
            print(f"Error processing modules for file {file_path}: {e}")
            return None

    # ---------- helpers ----------

    def _infer_crate(self, root: Dict[str, Any]) -> Optional[str]:
        for bucket in (
            "module_declarations",
            "functions",
            "type_definitions",
            "impl_blocks",
            "trait_method_signatures",
            "constant_definitions",
            "use_statements",
        ):
            for it in root.get(bucket, []) or []:
                if it.get("crate_name"):
                    return it.get("crate_name")
        return None

    def _infer_module_path(self, root: Dict[str, Any]) -> Optional[str]:
        for bucket in (
            "module_declarations",
            "functions",
            "type_definitions",
            "impl_blocks",
            "trait_method_signatures",
            "constant_definitions",
            "use_statements",
        ):
            for it in root.get(bucket, []) or []:
                if it.get("module_path") is not None:
                    return it.get("module_path")
        return None

    def _infer_fqp_from_any(self, node: Dict[str, Any]) -> Optional[str]:
        """Try to build '<crate>::<module_path>' or use a fully_qualified_path if present."""
        # Direct FQP (rare on declarations' container)
        fqp = node.get("fully_qualified_path")
        if fqp:
            return fqp

        crate = node.get("crate_name") or self._infer_crate(node)
        modp = node.get("module_path") if node.get("module_path") is not None else self._infer_module_path(node)
        if crate:
            return f"{crate}{('::' + modp) if modp else ''}"
        return None

    # ---------- discovery ----------

    def _get_module_files(self) -> List[str]:
        """
        Get all candidate JSON files. We include *.json but skip Haskell sidecars.
        Actual filtering happens in process_single_module_file.
        """
        files = list_files_recursive(self.json_path, pattern=".json")
        return [
            f
            for f in files
            if not (
                f.endswith(".hs.json")
                or f.endswith(".hs.type.typechecker.json")
                or f.endswith(".hs.types_code.json")
                or f.endswith(".hs.module_imports.json")
            )
        ]

    # ---------- public API ----------

    def load(self) -> Dict[str, List[Module]]:
        """
        Load all module declarations and update internal state.

        Returns:
            Dictionary of module names (FQP) to lists of Module objects
        """
        self.modulesPerName = {}

        for file_path in self._get_module_files():
            self.process_single_module_file(file_path)

        return self.modulesPerName

    def get_modules(self) -> Dict[str, List[Module]]:
        """
        Get all modules.

        Returns:
            Dict[module_name, List[Module]]
        """
        return self.modulesPerName
