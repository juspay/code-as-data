# code_as_data/models/constant_model.py
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict


class Constant(BaseModel):
    """`const` or `static` item in Rust."""

    name: str
    fully_qualified_path: str
    src_code: str
    src_location: str
    line_number_start: int
    line_number_end: int
    module_name: str

    # Optional metadata
    const_type:   Optional[Dict[str, Any]] = None
    visibility:   Optional[str] = None
    doc_comments: Optional[str] = None
    attributes:   Optional[List[Dict[str, Any]]] = None
    is_static:    bool = False

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True,
        populate_by_name=True,
    )

    @property
    def id(self) -> str:
        return self.fully_qualified_path

    def get_prompt(self) -> str:
        """
        Fenced Rust snippet for documentation / LLM usage.
        """
        return f"```rust\n{self.src_code}\n```"
