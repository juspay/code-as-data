# code_as_data/parsers/impl_block_parser.py
import json
from typing import Dict, List, Optional, Any

from . import list_files_recursive, error_trace
from code_as_data.models.impl_block_model import ImplBlock


class ImplBlockParser:
    """Parser for Rust `impl ... {}` blocks from FileAnalysis JSON dumps."""

    def __init__(self, json_path: str):
        """
        Initialize the impl-block parser.

        Args:
            json_path: Path to the Rust FileAnalysis JSON files
        """
        self.json_path = json_path
        self.implsPerModule: Dict[str, List[ImplBlock]] = {}

    # ---------- per-file processing ----------

    def process_single_impl_module(self, file_path: str) -> Optional[List[ImplBlock]]:
        """
        Process a single Rust FileAnalysis JSON and collect impl blocks.

        Args:
            file_path: Path to the FileAnalysis JSON

        Returns:
            List of ImplBlock objects for the inferred module if successful, None otherwise
        """
        try:
            with open(file_path, "r") as f:
                try:
                    obj = json.load(f)
                except json.JSONDecodeError:
                    return None  # Ignore empty or invalid JSON files

            # Only handle Rust FileAnalysis with impl_blocks
            if not isinstance(obj, dict) or "impl_blocks" not in obj:
                return None

            module_name = self._infer_module_name(obj, file_path)
            file_src = obj.get("file_path", file_path)

            impls_list: List[ImplBlock] = []
            for ib in obj.get("impl_blocks", []) or []:
                impl_obj = self._process_impl_block_data(ib, module_name, file_src)
                if impl_obj:
                    impls_list.append(impl_obj)

            if impls_list:
                # store under the inferred module
                self.implsPerModule.setdefault(module_name, []).extend(impls_list)
                return impls_list

            return None

        except Exception as e:
            error_trace(e)
            print(f"Error processing impl blocks for file {file_path}: {e}")
            return None

    # ---------- helpers ----------

    def _infer_module_name(self, root: Dict[str, Any], fallback: str) -> str:
        """
        Build a module name like '<crate>::<module_path>' from any bucket that provides it.
        Falls back to '<unknown_crate>' if nothing is present.
        """
        buckets = (
            "impl_blocks",
            "functions",
            "type_definitions",
            "use_statements",
            "trait_method_signatures",
            "constant_definitions",
            "module_declarations",
        )
        for b in buckets:
            for it in root.get(b, []) or []:
                crate = it.get("crate_name")
                modp = it.get("module_path") or ""
                if crate:
                    return f"{crate}{('::' + modp) if modp else ''}"
        return "<unknown_crate>"

    def _process_impl_block_data(
        self, ib: Dict[str, Any], module_name: str, file_src: str
    ) -> Optional[ImplBlock]:
        """
        Convert one impl-block dict into an ImplBlock model instance.
        """
        try:
            implementing_type = ib.get("implementing_type")
            trait_type = ib.get("trait_type")

            struct_name = None
            struct_fqp = None
            if implementing_type:
                struct_name = implementing_type.get("type_name")
                s_crate = implementing_type.get("crate_name")
                s_mod_path = implementing_type.get("module_path")
                if s_crate and s_mod_path and struct_name:
                    struct_fqp = f"{s_crate}::{s_mod_path}::{struct_name}"
                elif s_crate and struct_name:
                    struct_fqp = f"{s_crate}::{struct_name}"
                else:
                    struct_fqp = struct_name

            trait_name = None
            trait_fqp = None
            if trait_type:
                trait_name = trait_type.get("type_name")
                t_crate = trait_type.get("crate_name")
                t_mod_path = trait_type.get("module_path")
                if t_crate and t_mod_path and trait_name:
                    trait_fqp = f"{t_crate}::{t_mod_path}::{trait_name}"
                elif t_crate and trait_name:
                    trait_fqp = f"{t_crate}::{trait_name}"
                else:
                    trait_fqp = trait_name

            return ImplBlock(
                crate_name=ib.get("crate_name", module_name.split("::", 1)[0]),
                module_path=ib.get(
                    "module_path",
                    module_name.split("::", 1)[-1] if "::" in module_name else "",
                ),
                name=ib.get("name", ""),
                src_location=ib.get("src_location", file_src),
                src_code=ib.get("src_code", ""),
                line_number_start=ib.get("line_number_start", -1),
                line_number_end=ib.get("line_number_end", -1),
                implementing_type=implementing_type,
                trait_type=trait_type,
                visibility=ib.get("visibility"),
                doc_comments=ib.get("doc_comments"),
                attributes=ib.get("attributes"),
                struct_name=struct_name,
                struct_fqp=struct_fqp,
                trait_name=trait_name,
                trait_fqp=trait_fqp,
            )
        except Exception as e:
            error_trace(e)
            print(f"Error processing impl block: {e}")
            return None

    # ---------- discovery ----------

    def _get_module_files(self) -> List[str]:
        """
        Get all candidate JSON files. We include *.json but skip Haskell sidecars.
        Actual filtering happens in process_single_impl_module (requires 'impl_blocks').
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

    def load(self) -> Dict[str, List[ImplBlock]]:
        """
        Load all impl-block information and update internal state.

        Returns:
            Dictionary of module names to their impl-block lists
        """
        # Clear existing state
        self.implsPerModule = {}

        # Process each candidate file
        for file_path in self._get_module_files():
            self.process_single_impl_module(file_path)

        return self.implsPerModule

    def get_impl_blocks(self) -> Dict[str, List[ImplBlock]]:
        """
        Get all impl-blocks.

        Returns:
            Dict[module_name, List[ImplBlock]]
        """
        return self.implsPerModule
