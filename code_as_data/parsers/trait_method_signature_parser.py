# code_as_data/parsers/trait_method_signature_parser.py
import json
from typing import Dict, List, Optional, Any

from . import list_files_recursive, error_trace
from code_as_data.models.trait_method_signature_model import TraitMethodSignature


class TraitMethodSignatureParser:
    """Parser for Rust trait method signatures from FileAnalysis JSON dumps."""

    def __init__(self, json_path: str):
        """
        Initialize the parser.

        Args:
            json_path: Path to the Rust FileAnalysis JSON files
        """
        self.json_path = json_path
        # Keyed by module_name (e.g., "my_crate::foo::bar")
        self.traitSigsPerModule: Dict[str, List[TraitMethodSignature]] = {}

    # ───────────────────────── helpers ─────────────────────────

    @staticmethod
    def _fqp(crate_name: Optional[str], module_path: Optional[str]) -> str:
        """Build fully-qualified module name from crate and module_path."""
        crate = crate_name or "<unknown_crate>"
        modp = (module_path or "").strip(":")
        return f"{crate}{('::' + modp) if modp else ''}"

    @staticmethod
    def _normalize_attributes(attrs: Any) -> Optional[List[Dict[str, Any]]]:
        """
        The Rust visitor typically emits a list of strings for attributes.
        Convert to a list of dicts to satisfy the model type.
        """
        if attrs is None:
            return None
        if isinstance(attrs, list):
            out: List[Dict[str, Any]] = []
            for a in attrs:
                out.append({"raw": a} if isinstance(a, str) else a)
            return out
        # Unknown shape – best effort
        return [{"raw": str(attrs)}]

    # ───────────────────────── per-file ─────────────────────────

    def process_single_file(self, file_path: str) -> Optional[List[TraitMethodSignature]]:
        """
        Process a single Rust FileAnalysis JSON.

        Returns a list of TraitMethodSignature objects, or None.
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

        # Only consider Rust FileAnalysis-shaped JSONs
        if not isinstance(obj, dict) or "trait_method_signatures" not in obj:
            return None

        rows: List[TraitMethodSignature] = []
        for t in obj.get("trait_method_signatures", []) or []:
            try:
                module_name = self._fqp(t.get("crate_name"), t.get("module_path"))
                sig = TraitMethodSignature(
                    name=t.get("name"),
                    fully_qualified_path=t.get("fully_qualified_path"),
                    src_code=t.get("src_code", ""),
                    src_location=t.get("src_location", file_path),
                    line_number_start=t.get("line_number_start", -1),
                    line_number_end=t.get("line_number_end", -1),
                    module_name=module_name,
                    input_types=t.get("input_types"),
                    output_types=t.get("output_types"),
                    visibility=t.get("visibility"),
                    doc_comments=t.get("doc_comments"),
                    attributes=self._normalize_attributes(t.get("attributes")),
                    is_async=bool(t.get("is_async", False)),
                    is_unsafe=bool(t.get("is_unsafe", False)),
                )
                rows.append(sig)
            except Exception as e:
                error_trace(e)
                # continue on per-item failure
                continue

        if rows:
            # group into state by module_name
            for sig in rows:
                self.traitSigsPerModule.setdefault(sig.module_name, []).append(sig)
            return rows

        return None

    # ───────────────────────── discovery ─────────────────────────

    def _get_candidate_files(self) -> List[str]:
        """
        Gather all *.json files but skip Haskell sidecars.
        Actual filtering for trait signatures happens in process_single_file().
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

    def load(self) -> Dict[str, List[TraitMethodSignature]]:
        """
        Load all trait method signatures and update internal state.

        Returns:
            Dict[module_name, List[TraitMethodSignature]]
        """
        self.traitSigsPerModule = {}

        for file_path in self._get_candidate_files():
            # Each file may contribute zero or many signatures
            self.process_single_file(file_path)

        return self.traitSigsPerModule

    def get_signatures_for_module(self, module_name: str) -> Optional[List[TraitMethodSignature]]:
        """
        Convenience accessor to fetch signatures for a given module.
        """
        return self.traitSigsPerModule.get(module_name)

    def get_trait_method_signatures(self) -> Dict[str, List[TraitMethodSignature]]:
        """
        Get all trait method signatures.

        Returns:
            Dict[module_name, List[TraitMethodSignature]]
        """
        return self.traitSigsPerModule
