# code_as_data/models/trait_model.py
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any, List

class Trait(BaseModel):
    """Top-level `trait Foo { … }` definition in Rust."""

    name: str
    fully_qualified_path: str          # crate::module::Foo
    src_location: str
    module_name: str
    module_path: Optional[str] = None  
    crate_name: Optional[str] = None   


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
        For summarisation or chat-ops: return a one-liner declaring the trait.
        (Bodies are in `TraitMethodSignature`.)
        """
        return f"```rust\ntrait {self.name} {{ /* … */ }}\n```"
