import json
import re
import concurrent.futures
from typing import Dict, List, Optional, Tuple, Any

from . import list_files_recursive, get_module_name, error_trace
from src.models.function_model import Function


class FunctionParser:
    """Parser for function data from dump files."""

    def __init__(self, fdep_path: str):
        """
        Initialize the function parser.

        Args:
            fdep_path: Path to the function dump files
        """
        self.path = fdep_path
        self.data = {}
        self.top_lvl_functions = []
        self.module_name_path = {}
        self.code_string_dict = {}

    def _update_nested_key(self, d: Dict, keys: List[str], value: Any) -> None:
        """
        Update a nested dictionary key.

        Args:
            d: Dictionary to update
            keys: List of nested keys
            value: Value to set
        """
        current = d
        try:
            for key in keys[:-1]:
                if current is not None:
                    if current.get(key) is None:
                        current[key] = {}
                        current[key]["where_functions"] = {}
                    else:
                        if current[key].get("where_functions") is None:
                            current[key]["where_functions"] = {}
                    current = current[key]
                else:
                    current = {}
                    current["where_functions"] = {}
            current["where_functions"][keys[-1]] = value
        except Exception as e:
            error_trace(e)
            print("update_nested_key", e)

    def process_single_module(self, file_path: str) -> Tuple[bool, Optional[Dict]]:
        """
        Process a single module file and update the internal state.

        Args:
            file_path: Path to the module file

        Returns:
            Tuple of (success, processed data)
        """
        # Load function code if it exists
        module_name = get_module_name(self.path, file_path, ".hs.json")

        # Load and process the main file
        try:
            with open(file_path, "r") as f:
                file_data = json.load(f)
                # Update internal state
                local_fdep = self._process_module_data(
                    file_path, file_data, module_name
                )

                self.module_name_path[module_name] = file_path.replace(
                    (self.path + "/"), ""
                ).replace(".json", "")

                # Update or add to existing data
                self.data[module_name] = local_fdep

                # Update top level functions
                new_functions = list(local_fdep.keys())
                self.top_lvl_functions.extend(new_functions)

                return (True, self.data[module_name])
        except Exception as e:
            error_trace(e)
            print(f"Error processing file {file_path}: {e}")
            return (False, None)

    def _process_module_data(self, file_path: str, obj: Dict, module_name: str) -> Dict:
        """
        Process the module data and return local fdep dictionary.

        Args:
            file_path: Path to the module file
            obj: Module data object
            module_name: Name of the module

        Returns:
            Dictionary of processed function data
        """
        local_fdep = {}
        function_code_path = file_path.replace(".hs.json", ".hs.function_code.json")

        try:
            with open(function_code_path) as code_string:
                self.code_string_dict[module_name] = json.load(code_string)
        except Exception as e:
            error_trace(e)
            print(f"Error loading function code from {function_code_path}: {e}")

        for functionsName, functionData in obj.items():
            if not "::" in functionsName:
                # Handle top-level functions
                fName = functionsName.replace("$_in$", "")
                srcLoc = (
                    functionsName.replace("$_in$", "").split("**")[1]
                    if "**" in functionsName
                    else ""
                )

                try:
                    local_fdep[fName] = {
                        "function_name": fName,
                        "src_loc": srcLoc,
                        "functions_called": [],
                    }

                    if (
                        self.code_string_dict.get(module_name, {}).get(fName)
                        is not None
                    ):
                        local_fdep[fName]["stringified_code"] = (
                            self.code_string_dict[module_name]
                            .get(fName, {})
                            .get("parser_stringified_code", "")
                        )
                        local_fdep[fName]["line_number_start"] = (
                            self.code_string_dict[module_name]
                            .get(fName, {})
                            .get("line_number", [-1, -1])[0]
                        )
                        local_fdep[fName]["line_number_end"] = (
                            self.code_string_dict[module_name]
                            .get(fName, {})
                            .get("line_number", [-1, -1])[1]
                        )

                    for i in functionData:
                        if i and i.get("typeSignature") is not None:
                            local_fdep[fName]["function_signature"] = i.get(
                                "typeSignature"
                            )
                        elif i and i.get("expr") is not None:
                            local_fdep[fName]["functions_called"].append(i.get("expr"))
                        elif i and i.get("functionIO") is not None:
                            local_fdep[fName]["function_input"] = i.get(
                                "functionIO", {}
                            ).get("inputs")
                            local_fdep[fName]["function_output"] = i.get(
                                "functionIO", {}
                            ).get("outputs")

                except Exception as e:
                    error_trace(e)
                    print(f"Error processing function {fName}: {e}")

            else:
                # Handle nested functions
                parentFunctions = functionsName.replace("$_in$", "").split("::")
                (currentFunctionName, currentFunctionSrcLocation) = (
                    parentFunctions[(len(parentFunctions) - 1)].split("**")
                    if "**" in parentFunctions[(len(parentFunctions) - 1)]
                    else (parentFunctions[(len(parentFunctions) - 1)], "")
                )

                currentFunctionDict = {
                    "function_name": currentFunctionName,
                    "src_loc": currentFunctionSrcLocation,
                    "functions_called": [],
                }

                for i in functionData:
                    if i and i.get("typeSignature") is not None:
                        currentFunctionDict["function_signature"] = i.get(
                            "typeSignature"
                        )
                    elif i and i.get("expr") is not None:
                        currentFunctionDict["functions_called"].append(i.get("expr"))

                self._update_nested_key(
                    local_fdep, parentFunctions, currentFunctionDict
                )

        # Remove duplicates from functions_called
        self._deduplicate_functions_called(local_fdep)

        return local_fdep

    def _deduplicate_functions_called(self, local_fdep: Dict) -> None:
        """
        Remove duplicate function calls from each function.

        Args:
            local_fdep: Local function dependency dictionary
        """
        for functionName, functionData in local_fdep.items():
            functions_called = functionData.get("functions_called", [])
            unique_elements = {}

            for item in functions_called:
                if item is not None:
                    key = (
                        item.get("_type", "")
                        + "**"
                        + item.get("name", "")
                        + "**"
                        + item.get("module_name", "")
                        + "**"
                        + item.get("package_name", "")
                    )
                    unique_elements[key] = item

            local_fdep[functionName]["functions_called"] = list(
                unique_elements.values()
            )

    def load_all_files(self) -> Dict:
        """
        Load all function files in the directory.

        Returns:
            Dictionary of processed function data
        """
        files = list_files_recursive(self.path, pattern=".hs.json")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_file = {
                executor.submit(self.process_single_module, file): file
                for file in files
            }
            for future in concurrent.futures.as_completed(future_to_file):
                file = future_to_file[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"Error reading {file}: {e}")

        return self.data

    def get_functions(self) -> List[Function]:
        """
        Convert processed data to Function objects.

        Returns:
            List of Function objects
        """
        functions = []

        for module_name, module_data in self.data.items():
            for function_name, function_body in module_data.items():
                clean_function_name = (
                    function_name.split("**")[0]
                    if "**" in function_name
                    else function_name
                )

                # Extract line numbers
                line_number_start = -1
                line_number_end = -1

                if (
                    function_body.get("src_loc")
                    and function_body["src_loc"] != "<no location info>"
                ):
                    if function_body.get("line_number_start") is None:
                        try:
                            line_number_start = (
                                int(function_body["src_loc"].split(":")[1])
                                if ":" in function_body["src_loc"]
                                else -1
                            )
                            line_number_end = line_number_start
                        except Exception as e:
                            # Try pattern like (70,1)-(71,20)
                            pattern = r".*:(\d+),(\d+)-\((\d+),(\d+)\)"
                            match = re.match(pattern, function_body["src_loc"])
                            if match:
                                line_number_start = int(match.group(1))
                                line_number_end = int(match.group(3))
                    else:
                        line_number_start = function_body["line_number_start"]
                        line_number_end = function_body["line_number_end"]

                # Create Function object
                function = Function(
                    function_signature=function_body.get("function_signature"),
                    function_name=clean_function_name,
                    raw_string=function_body.get("stringified_code"),
                    src_loc=function_body.get("src_loc"),
                    module_name=module_name,
                    _type="_function",
                    where_functions=function_body.get("where_functions", {}),
                    functions_called=function_body.get("functions_called", []),
                    line_number_start=line_number_start,
                    line_number_end=line_number_end,
                    function_input=function_body.get("function_input"),
                    function_output=function_body.get("function_output"),
                )

                functions.append(function)

        return functions
