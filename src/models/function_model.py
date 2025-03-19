from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class FunctionCalled(BaseModel):
    """Model representing a called function within another function."""

    module_name: Optional[str] = None
    function_name: Optional[str] = None
    name: Optional[str] = None  # Alias for function_name
    package_name: Optional[str] = None
    src_loc: Optional[str] = None
    type_enum: str
    id: Optional[str] = None
    function_signature: Optional[str] = None

    def __init__(self, **data):
        # Rename 'name' to 'function_name' if needed
        if "name" in data and not data.get("function_name"):
            data["function_name"] = data["name"]

        # Construct id if not provided
        if not data.get("id") and data.get("module_name") and data.get("function_name"):
            data["id"] = f"{data['module_name']}:{data['function_name']}"

        # Resolve type_enum
        if "_type" in data and not data.get("type_enum"):
            data["type_enum"] = data["_type"]

        super().__init__(**data)


class WhereFunction(BaseModel):
    """Model representing a 'where' function defined within another function."""

    module_name: str
    function_name: str
    id: Optional[str] = None
    function_signature: Optional[str] = None
    src_loc: Optional[str] = None
    raw_string: Optional[str] = None
    type_enum: str = "where_function"
    functions_called: List[FunctionCalled] = Field(default_factory=list)
    where_functions: Dict[str, "WhereFunction"] = Field(default_factory=dict)


class Function(BaseModel):
    """Main function model."""

    # Core attributes
    module_name: str
    function_name: str
    id: Optional[str] = None
    function_signature: Optional[str] = None
    src_loc: Optional[str] = None
    raw_string: Optional[str] = None
    type_enum: str
    line_number_start: int
    line_number_end: int
    function_input: Optional[List[Any]] = None
    function_output: Optional[List[Any]] = None

    # Nested structures
    functions_called: List[FunctionCalled] = Field(default_factory=list)
    where_functions: Dict[str, WhereFunction] = Field(default_factory=dict)

    def __init__(self, **data):
        # Construct id if not provided
        if not data.get("id") and data.get("module_name") and data.get("function_name"):
            data["id"] = f"{data.get('module_name')}:{data.get('function_name')}"

        # Handle functions_called conversion
        if "functions_called" in data:
            data["functions_called"] = [
                FunctionCalled(
                    module_name=i.get("module_name"),
                    name=i.get("name"),
                    package_name=i.get("package_name"),
                    src_loc=i.get("src_loc"),
                    _type=i.get("type_enum", i.get("_type", "")),
                )
                for i in data["functions_called"]
            ]

        # Handle type_enum conversion
        if "_type" in data and not data.get("type_enum"):
            data["type_enum"] = data["_type"]

        # Handle where_functions conversion
        if "where_functions" in data:
            where_functions_dict = {}
            for function_name, i in data["where_functions"].items():
                # Split function_name if it contains "**"
                function_name_ = function_name.split("**")[0]
                src_loc = (
                    function_name.split("**")[1] if "**" in function_name else None
                )

                where_function_data = {
                    "module_name": data.get("module_name"),
                    "function_name": function_name_,
                    "function_signature": i.get("function_signature"),
                    "raw_string": i.get("raw_string", ""),
                    "src_loc": i.get("src_loc", src_loc),
                    "functions_called": i.get("functions_called", []),
                    "where_functions": i.get("where_functions", {}),
                }

                where_functions_dict[function_name] = WhereFunction(
                    **where_function_data
                )

            data["where_functions"] = where_functions_dict

        super().__init__(**data)

    def get_function_prompt(self) -> Optional[str]:
        """Generate a formatted representation of the function for prompts."""
        if self.function_signature is None or "$$" in self.function_name:
            return None

        function_str = ""
        if self.function_signature:
            function_str += f"{self.function_name} :: {self.function_signature}\n"

        if self.raw_string:
            function_str += self.raw_string

        if function_str:
            function_str = f"```haskell\n{function_str}\n```"

        return function_str
