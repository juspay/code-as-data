from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class Import(BaseModel):
    """Model representing an import statement."""

    src_loc: str
    module_name: Optional[str] = None
    package_name: Optional[str] = None
    is_boot_source: bool = False
    is_safe: Optional[bool] = None
    is_implicit: Optional[bool] = None
    as_module_name: Optional[str] = None
    qualified_style: Optional[str] = None
    is_hiding: bool = False
    hiding_specs: Optional[List[str]] = None
    line_number_start: int
    line_number_end: int

    path: Optional[str] = None          # raw `use foo::bar::Baz;`
    visibility: Optional[str] = None    # "pub", "pub(crate)", None …

    model_config = ConfigDict(
        arbitrary_types_allowed=True, from_attributes=True, populate_by_name=True
    )

    def __init__(self, **data):
        # Handle nested hidingSpec
        if "hidingSpec" in data:
            hiding_spec = data.get("hidingSpec", {})
            data["is_hiding"] = (
                hiding_spec.get("isHiding", False) if hiding_spec else False
            )
            data["hiding_specs"] = hiding_spec.get("names") if hiding_spec else None

        # Correct potential key naming issues
        if "moduleName'" in data:
            data["module_name"] = data.pop("moduleName'")

        # Handle qualified style
        if "qualifiedStyle" in data:
            qualified_style = data.get("qualifiedStyle", {})
            data["qualified_style"] = (
                qualified_style.get("tag")
                if isinstance(qualified_style, dict)
                else qualified_style
            )

        # Ensure is_boot_source is correctly set
        if "is_boot_source" in data and isinstance(data["is_boot_source"], str):
            data["is_boot_source"] = data.get("as_module_name") is not None

        super().__init__(**data)

    def get_prompt(self) -> str:
        """Generate a JSON representation of the import for prompting."""
        return self.model_dump_json(indent=4)
