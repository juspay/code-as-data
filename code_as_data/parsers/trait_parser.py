# code_as_data/parsers/trait_parser.py
import json
from typing import Dict, List, Optional, Any

from . import list_files_recursive, error_trace
from code_as_data.models.trait_model import Trait


class TraitParser:
    """Parser for Rust trait declarations from FileAnalysis JSON dumps."""

    def __init__(self, json_path: str):
        """
        Initialize the parser.

        Args:
            json_path: Path to the Rust FileAnalysis JSON files
        """
        self.json_path = json_path
        # Keyed by module_name (e.g., "my_crate::foo::bar")
        self.traitsPerModule: Dict[str, List[Trait]] = {}

    # ───────────────────────── helpers ─────────────────────────

    @staticmethod
    def _fqp(crate_name: Optional[str], module_path: Optional[str]) -> str:
        """Build fully-qualified module name from crate and module_path."""
        crate = crate_name or "<unknown_crate>"
        modp = (module_path or "").strip(":")
        return f"{crate}{('::' + modp) if modp else ''}"

    # ───────────────────────── per-file ─────────────────────────

    def process_single_file(self, file_path: str) -> Optional[List[Trait]]:
        """
        Process a single Rust FileAnalysis JSON.

        Returns a list of Trait objects, or None.
        """
        try:
            with open(file_path, "r") as f:
                try:
                    obj = json.load(f)
                except json.JSONDecodeError:
                    return None  # Ignore empty or invalid JSON files
        except Exception as e:
            error_trace(e)
            return None

        # Only consider Rust FileAnalysis-shaped JSONs that expose `impl_blocks`
        if not isinstance(obj, dict) or "impl_blocks" not in obj:
            return None

        rows: List[Trait] = []
        for ib in obj.get("impl_blocks", []) or []:
            try:
                if ib.get("trait_type"):
                    t = ib["trait_type"]
                    module_name = self._fqp(t.get("crate_name"), t.get("module_path"))
                    rows.append(
                        Trait(
                            name=t.get("type_name"),
                            fully_qualified_path=self._fqp(
                                t.get("crate_name"), t.get("module_path")
                            )
                            + "::"
                            + t.get("type_name"),
                            src_location=t.get("src_location", file_path),
                            module_name=module_name,
                            module_path=t.get("module_path"),
                            crate_name=t.get("crate_name"),
                        )
                    )
            except Exception as e:
                error_trace(e)
                # continue on per-item failure
                continue

        if rows:
            for tr in rows:
                self.traitsPerModule.setdefault(tr.module_name, []).append(tr)
            return rows

        return None

    # ───────────────────────── discovery ─────────────────────────

    def _get_candidate_files(self) -> List[str]:
        """
        Gather all *.json files but skip Haskell sidecars.
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

    # ───────────────────────── public API ─────────────────────────

    def load(self) -> Dict[str, List[Trait]]:
        """
        Load all trait declarations and update internal state.

        Returns:
            Dict[module_name, List[Trait]]
        """
        self.traitsPerModule = {}

        for file_path in self._get_candidate_files():
            self.process_single_file(file_path)

        return self.traitsPerModule

    def get_traits_for_module(self, module_name: str) -> Optional[List[Trait]]:
        """
        Convenience accessor to fetch traits for a given module.
        """
        return self.traitsPerModule.get(module_name)

    def get_traits(self) -> Dict[str, List[Trait]]:
        """
        Get all traits.

        Returns:
            Dict[module_name, List[Trait]]
        """
        return self.traitsPerModule
