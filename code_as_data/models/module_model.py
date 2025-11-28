# code_as_data/models/module_model.py
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class Module(BaseModel):
    """
    Language-agnostic code module.

    For Rust:
      - name: fully-qualified module path, e.g. "my_crate::foo::bar"
      - path: source file path, e.g. "/workspace/src/foo/bar.rs"
    """

    # Core fields that map to ORM columns
    name: str                 # maps to ORM Module.name
    path: str                 # maps to ORM Module.path

    # Optional metadata your Rust visitor can provide (not stored in ORM by default)
    fully_qualified_path: Optional[str] = None
    crate_name: Optional[str] = None
    module_path: Optional[str] = None     # logical module path; often same as `name`
    visibility: Optional[str] = None
    doc_comments: Optional[str] = None
    attributes: Optional[List[Dict[str, Any]]] = None
    line_number: Optional[int] = None

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True,
        populate_by_name=True,
    )

    @property
    def id(self) -> str:
        # Unique-ish composite key for your pipeline / caches
        return f"{self.name}@{self.path}"

    def get_prompt(self) -> str:
        # Handy snippet for docs/LLM contexts
        leaf = self.name.split("::")[-1] if self.name else "module"
        return f"```rust\nmod {leaf} {{ /* … */ }}\n```"


# # ---------- ORM helper (uses your SQLAlchemy models) ----------
# def get_or_create_module(session, name: str, path: str):
#     """
#     Lookup a Module row by (name, path). If it doesn't exist, create it.
#     Returns the ORM object with a populated `id`.
#     """
#     # Adjust this import path to wherever your ORM 'Module' lives.
#     from ..db.model import Module as ORMModule  # e.g. code_as_data/db/model.py

#     mod = session.query(ORMModule).filter_by(name=name, path=path).one_or_none()
#     if mod is None:
#         mod = ORMModule(name=name, path=path)
#         session.add(mod)
#         session.flush()  # ensures mod.id is assigned by the DB
#     return mod
