import json
from typing import Dict, List, Optional, Any

from . import list_files_recursive, error_trace
from code_as_data.models.constant_model import Constant


class ConstantParser:
    """Parser for Rust constants (`const` / `static`) from FileAnalysis JSONs."""

    def __init__(self, base_path: str):
        """
        Initialize the constant parser.

        Args:
            base_path: Root path where FileAnalysis JSONs live (same root you pass to other parsers)
        """
        self.path = base_path
        self.constants_per_module: Dict[str, List[Constant]] = {}

    # ---------- helpers ---------------------------------------------------
    def _infer_module_name(self, obj: Dict[str, Any]) -> str:
        """
        Derive something like "<crate>::<module_path>" from any bucket present.
        Falls back to a best-effort using fully_qualified_path or an unknown marker.
        """
        buckets = (
            "constant_definitions",
            "functions",
            "type_definitions",
            "impl_blocks",
            "trait_method_signatures",
            "use_statements",
            "module_declarations",
        )
        for bucket in buckets:
            for it in (obj.get(bucket) or []):
                crate = it.get("crate_name")
                modp = it.get("module_path") or ""
                if crate:
                    return f"{crate}{('::' + modp) if modp else ''}"
                fqp = it.get("fully_qualified_path")
                if fqp:
                    return fqp.rsplit("::", 1)[0] if "::" in fqp else fqp
        return "<unknown_crate>"

    def _file_is_haskell_sidecar(self, path: str) -> bool:
        return (
            path.endswith(".hs.json")
            or path.endswith(".hs.module_imports.json")
            or path.endswith(".hs.type.typechecker.json")
            or path.endswith(".hs.types_code.json")
        )

    # ---------- public API ------------------------------------------------
    def load(self) -> Dict[str, List[Constant]]:
        """
        Load all Rust constants and update internal state.

        Returns:
            Dict[module_name, List[Constant]]
        """
        self.constants_per_module = {}

        # Scan for candidate JSONs (exclude all Haskell sidecars)
        candidates = [
            f for f in list_files_recursive(self.path, pattern=".json")
            if not self._file_is_haskell_sidecar(f)
        ]

        for file_path in candidates:
            try:
                with open(file_path, "r") as f:
                    obj = json.load(f)
            except Exception:
                # not a JSON we care about
                continue

            # Only consider FileAnalysis-like objects with constants
            if not isinstance(obj, dict) or "constant_definitions" not in obj:
                continue

            module_name = self._infer_module_name(obj)
            file_src = obj.get("file_path", file_path)

            rows: List[Constant] = []
            for c in (obj.get("constant_definitions") or []):
                # Prefer provided FQP; otherwise synthesize from crate/module/name
                fqp = c.get("fully_qualified_path")
                if not fqp:
                    crate = c.get("crate_name")
                    modp  = c.get("module_path")
                    name  = c.get("name")
                    parts = [p for p in [crate, modp, name] if p]
                    fqp = "::".join(parts) if parts else (name or "")

                try:
                    rows.append(
                        Constant(
                            name=c.get("name", ""),
                            fully_qualified_path=fqp,
                            src_code=c.get("src_code", ""),
                            src_location=c.get("src_location", file_src),
                            line_number_start=c.get("line_number_start", -1),
                            line_number_end=c.get("line_number_end", -1),
                            module_name=module_name,
                            const_type=c.get("const_type"),
                            visibility=c.get("visibility"),
                            doc_comments=c.get("doc_comments"),
                            attributes=c.get("attributes"),
                            is_static=bool(c.get("is_static", False)),
                        )
                    )
                except Exception as e:
                    error_trace(e)
                    continue

            if rows:
                self.constants_per_module.setdefault(module_name, []).extend(rows)

        return self.constants_per_module

    def get_constants_for_module(self, module_name: str) -> Optional[List[Constant]]:
        """
        Get constants for a specific module (Rust only).

        Args:
            module_name: "<crate>::<module_path>"

        Returns:
            List of Constant for that module if found, else None
        """
        return self.constants_per_module.get(module_name)

    def get_constants(self) -> Dict[str, List[Constant]]:
        """
        Get all constants.

        Returns:
            Dict[module_name, List[Constant]]
        """
        return self.constants_per_module
