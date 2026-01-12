from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class ImplBlock(BaseModel):
    """
    Rust `impl … {}` definition.

    A row is produced for every inherent `impl` or `impl Trait for Type` block.
    """

    # core identity -------------------------------------------------------
    crate_name: str
    module_path: str
    name: str
    src_location: str
    src_code: str
    line_number_start: int
    line_number_end: int

    # relationships / descriptors ----------------------------------------
    struct_name: Optional[str] = None
    struct_fqp: Optional[str] = None
    trait_name: Optional[str] = None
    trait_fqp: Optional[str] = None
    implementing_type: Optional[Dict[str, Any]] = None
    trait_type:        Optional[Dict[str, Any]] = None

    visibility:        Optional[str] = None
    doc_comments:      Optional[str] = None
    attributes:        Optional[List[Dict[str, Any]]] = None 

    # config --------------------------------------------------------------
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True,
        populate_by_name=True,
    )

    # helpers -------------------------------------------------------------
    @property
    def id(self) -> str:
        """
        Unique identifier used in graphs/queries:
        `module_path::impl::<name>` (crate prefix is optional in your tooling).
        """
        return f"{self.module_path}::impl::{self.name}"

    def get_prompt(self) -> str:
        """
        Return the `impl` block as a fenced Rust code snippet.

        The resulting string is ready for inclusion in generated
        documentation, review comments, or downstream processing
        that expects a Markdown-formatted code block.

        Returns
        -------
        str
            The implementation block’s source, wrapped in
            triple-backtick ```rust``` fences.
        """
        return f"```rust\n{self.src_code}\n```"
