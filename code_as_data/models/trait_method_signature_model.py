# code_as_data/models/trait_method_signature_model.py
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class TraitMethodSignature(BaseModel):
    """A single signature line inside a trait – no default body."""

    name: str
    fully_qualified_path: str
    src_code: str
    src_location: str
    line_number_start: int
    line_number_end: int
    module_name: str

    # Extra Rust metadata
    input_types:  Optional[List[Dict[str, Any]]] = None
    output_types: Optional[List[Dict[str, Any]]] = None
    visibility:   Optional[str] = None
    doc_comments: Optional[str] = None
    attributes:   Optional[List[Dict[str, Any]]] = None 
    is_async: bool = False
    is_unsafe: bool = False

    # FK filled by importer (can stay None)
    trait_id: Optional[int] = None

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
        Return the signature as a fenced Rust snippet.
        """
        return f"```rust\n{self.src_code}\n```"
