from typing import Optional
from pydantic import BaseModel, ConfigDict


class Class(BaseModel):
    """Model representing a class."""

    module_name: str
    class_name: str
    class_definition: str
    src_location: str
    line_number_start: int
    line_number_end: int

    model_config = ConfigDict(
        arbitrary_types_allowed=True, from_attributes=True, populate_by_name=True
    )

    def get_prompt(self) -> str:
        """Return the class definition for prompting."""
        return self.class_definition

    @property
    def id(self) -> str:
        """Generate a unique ID for the class."""
        return f"{self.module_name}:{self.class_name}"
