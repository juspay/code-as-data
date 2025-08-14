from pydantic import BaseModel
from typing import List
from .function_model import Function


class Instance(BaseModel):
    """Model representing an instance."""

    instanceDefinition: str
    instance_id: str
    module_name: str
    src_loc: str
    instance_signature: str
    line_number_start: int
    line_number_end: int
    functions: List[Function]

    def __hash__(self):
        return hash(self.instance_signature)

    def __eq__(self, other):
        if isinstance(other, Instance):
            return self.src_loc == other.src_loc
        return False

    @property
    def id(self) -> str:
        """Generate a unique ID for the instance."""
        return f"{self.module_name}:{self.instanceDefinition}"
