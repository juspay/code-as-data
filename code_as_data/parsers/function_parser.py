import json
import re
import os
import concurrent.futures
from typing import Dict, List, Optional, Tuple, Any
import time
import multiprocessing
import io

from . import list_files_recursive, get_module_name, error_trace
from code_as_data.models.function_model import Function


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

    def load(self) -> Dict[str, List[Function]]:
        """
        Process function dump files and return the parsed data.

        Returns:
            Dictionary of module names to functions
        """
        # Load function data
        self.load_all_files()

        functions = self.get_functions()

        functions_by_module = {}
        for function in functions:
            if function.module_name not in functions_by_module:
                functions_by_module[function.module_name] = []
            functions_by_module[function.module_name].append(function)

        return functions_by_module

    def load_all_files(self) -> Dict:
        """
        Load all function files in the directory using a sequential approach optimized for I/O.

        This approach focuses on minimizing I/O overhead and serialization costs.

        Returns:
            Dictionary of processed function data
        """
        # Get all function files
        overall_start = time.time()
        files = list_files_recursive(self.path, pattern=".hs.json")
        print(f"Found {len(files)} function files to process")

        if not files:
            print("No files found. Check the path and pattern.")
            return {}

        # Clear existing data
        self.data = {}
        self.module_name_path = {}
        self.top_lvl_functions = []

        # Pre-calculate module names for all files
        module_names = {}
        module_paths = {}
        for file_path in files:
            module_name = get_module_name(self.path, file_path, ".hs.json")
            module_names[file_path] = module_name
            module_paths[module_name] = file_path.replace(
                (self.path + "/"), ""
            ).replace(".json", "")

        # Pre-load all code string data in a single pass
        code_strings = {}
        for file_path in files:
            module_name = module_names[file_path]
            function_code_path = file_path.replace(".hs.json", ".hs.function_code.json")
            try:
                with open(function_code_path, "r") as f:
                    code_strings[module_name] = json.load(f)
            except Exception:
                code_strings[module_name] = {}

        # Process files
        processed_files = 0
        start_time = time.time()
        update_interval = max(
            1, min(1000, len(files) // 20)
        )  # Update progress every ~5%

        # Process all files sequentially with optimized I/O
        for file_path in files:
            module_name = module_names[file_path]

            try:
                # Process the file
                file_data = dict()
                with open(file_path, "r") as y:
                    try:
                        file_data = json.load(y)
                    except Exception as _:
                        y.close()
                    # if the file is JSONL format , preprocess to match the dict[key] format
                    # {"typeSignature":"Application -> Application -> Application","key":"$_in$appDecider**app/Main.hs:266:1-10"}
                        with open(file_path, "r") as f:
                            try:
                                tmp_data = set(f.readlines())
                                for i in tmp_data:
                                    try:
                                        t = json.loads(i)
                                    except Exception as e:
                                        pass
                                        # print(i)
                                    key = t.get("key")
                                    if file_data.get(key) == None:
                                        file_data[key] = []
                                    file_data[key].append(t)
                            except Exception as e:
                                error_trace(e)
                            finally:
                                f.close()

                # Get code strings for this module
                module_code_strings = code_strings.get(module_name, {})

                # Process the data
                local_fdep = self._process_module_data(
                    file_path, file_data, module_name, module_code_strings
                )

                # Update data structures
                self.data[module_name] = local_fdep
                self.module_name_path[module_name] = module_paths[module_name]
                self.top_lvl_functions.extend(list(local_fdep.keys()))

            except Exception as e:
                print(f"Error processing file {file_path}: {e}")
                error_trace(e)

            # Update progress
            processed_files += 1
            if processed_files % update_interval == 0 or processed_files == len(files):
                elapsed = time.time() - start_time
                files_per_second = processed_files / elapsed if elapsed > 0 else 0
                remaining = (
                    (len(files) - processed_files) / files_per_second
                    if files_per_second > 0
                    else 0
                )

                print(
                    f"Progress: {processed_files}/{len(files)} files processed "
                    f"({files_per_second:.1f} files/sec, ~{remaining:.1f}s remaining)"
                )

        # Report completion
        total_time = time.time() - overall_start
        print(
            f"Completed processing {len(self.data)} modules in {total_time:.2f} seconds "
            f"({len(files)/total_time:.1f} files/sec)"
        )

        return self.data

    def _process_module_data(
        self, file_path: str, obj: Dict, module_name: str, code_string_dict: Dict
    ) -> Dict:
        """
        Process the module data and return local fdep dictionary.

        Args:
            file_path: Path to the module file
            obj: Module data object
            module_name: Name of the module
            code_string_dict: Dictionary of function code strings

        Returns:
            Dictionary of processed function data
        """
        local_fdep = {}

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

                    if code_string_dict.get(fName) is not None:
                        local_fdep[fName]["stringified_code"] = code_string_dict.get(
                            fName, {}
                        ).get("parser_stringified_code", "")
                        local_fdep[fName]["line_number_start"] = code_string_dict.get(
                            fName, {}
                        ).get("line_number", [-1, -1])[0]
                        local_fdep[fName]["line_number_end"] = code_string_dict.get(
                            fName, {}
                        ).get("line_number", [-1, -1])[1]

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
                        except Exception:
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
