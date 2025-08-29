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
        files = list_files_recursive(
            self.path,
            pattern=[".hs.json", ".json"]     # rust dumps end with plain `.json`
        )

        # files = [
        #     f for f in files
        #     if (
        #         f.endswith(".hs.json")
        #         or (f.endswith(".json") and "/crates/" in f)
        #     )
        # ]
        files = [
            f for f in files
            if f.endswith(".hs.json") or (f.endswith(".json") and not f.endswith(".hs.json"))
        ]

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
            ext = ".hs.json" if file_path.endswith(".hs.json") else ".json"
            module_name = get_module_name(self.path, file_path, ext)
            module_names[file_path] = module_name
            module_paths[module_name] = file_path.replace(
                (self.path + "/"), ""
            ).replace(".json", "")

        #Pre-load all code string data in a single pass (Haskell only)
        code_strings = {}
        functions_vs_instances_used = {}
        # Types.hs.function_instance_mapping.json
        for file_path in files:
            if not file_path.endswith(".hs.json"):
                continue  # ← rust files have no side-car dumps
            module_name = module_names[file_path]
            function_code_path = file_path.replace(".hs.json", ".hs.function_code.json")
            try:
                with open(function_code_path, "r") as f:
                    code_strings[module_name] = json.load(f)
            except Exception:
                code_strings[module_name] = {}

            def get_function_name_from_name_stable_string(name):
                return name.split("$")[-1]

            instances_used_per_function_path = file_path.replace(
                ".hs.json", ".hs.function_instance_mapping.json"
            )

            try:
                with open(instances_used_per_function_path, "r") as f:
                    functions_vs_instances_used[module_name] = json.load(f)
                    functions_vs_instances_used[module_name] = {
                        get_function_name_from_name_stable_string(k): [s for (f,s) in v]
                        for k, v in functions_vs_instances_used[module_name].items()
                    }
            except Exception:
                functions_vs_instances_used[module_name] = {}

        with open("functions_vs_instances_used.json","w") as f:
            json.dump(functions_vs_instances_used,f,indent=4)
        
        # Process files
        processed_files = 0
        start_time = time.time()
        update_interval = max(
            1, min(1000, len(files) // 20)
        )  # Update progress every ~5%

        # Process all files sequentially with optimized I/O
        for file_path in files:
            # decide once for this file
            is_rust = file_path.endswith(".json") and not file_path.endswith(".hs.json")
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
                                        key = t.get("key")
                                        if file_data.get(key) is None:
                                            file_data[key] = []
                                        file_data[key].append(t)
                                    except Exception as e:
                                        # print(i)
                                        pass
                            except Exception as e:
                                error_trace(e)
                            finally:
                                f.close()

                # Haskell side-cars exist only for .hs.json dumps
                module_code_strings = (
                    {} if is_rust else code_strings.get(module_name, {})
                )
                module_functions_vs_instances_used = (
                    {} if is_rust else functions_vs_instances_used.get(module_name, {})
                )
                # Process the data
                if is_rust:
                    if not isinstance(file_data, dict) or "functions" not in file_data:
                        local_fdep = {}
                    else:
                        local_fdep = self._process_rust_module(
                            file_path,
                            file_data,
                            module_name,
                        )
                else:
                    local_fdep = self._process_module_data(
                        file_path,
                        file_data,
                        module_name,
                        module_code_strings,
                        module_functions_vs_instances_used,
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
        self,
        file_path: str,
        obj: Dict,
        module_name: str,
        code_string_dict: Dict,
        module_functions_vs_instances_used: Dict,
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

                    if module_functions_vs_instances_used.get(fName.split("**")[0].split("$")[-1]) != None:
                        local_fdep[fName]["instances_used"] = module_functions_vs_instances_used.get(fName.split("**")[0].split("$")[-1])

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

    def _ensure_type_in_calls(self, calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure all function calls have a _type field for compatibility."""
        for call in calls:
            if "_type" not in call and "call_type" not in call:
                # Set default type based on is_method field if available
                if call.get("is_method", False):
                    call["_type"] = "method"
                else:
                    call["_type"] = "function"
            elif "call_type" in call and "_type" not in call:
                # Use call_type as _type for Rust compatibility
                call["_type"] = call["call_type"]
        return calls

    # ───────────────────────────  R U S T  ────────────────────────────
    def _process_rust_module(
        self,
        file_path: str,
        obj: Dict,
        module_name: str,
    ) -> Dict[str, Any]:
        """
        Convert a Rust f-dep JSON (visitor.rs output) into the same nested
        dict shape that Haskell processing produces.
        """
        local: Dict[str, Any] = {}

        # The visitor writes {"functions":[{…}, …]}
        for fn in obj.get("functions", []):
            fname = fn["name"]
            # normalize nested closures to our where_functions shape
            rust_where = {}
            for wname, wf in (fn.get("where_functions") or {}).items():
                rust_where[wname] = {
                    "function_name": wname,
                    "src_loc": wf.get("src_location"),
                    "raw_string": wf.get("src_code"),
                    "functions_called": self._ensure_type_in_calls(
                        (wf.get("functions_called", []) or []) + (wf.get("methods_called", []) or [])
                    ),
                    # carry Rust extras so Function.__init__ can fan them into WhereFunction
                    "fully_qualified_path": wf.get("fully_qualified_path"),
                    "input_types": wf.get("input_types"),
                    "output_types": wf.get("output_types"),
                    "types_used": wf.get("types_used"),
                    "literals_used": wf.get("literals_used"),
                    "methods_called": wf.get("methods_called"),
                    "is_method": wf.get("is_method"),
                    "self_type": wf.get("self_type"),
                    "visibility": wf.get("visibility"),
                    "doc_comments": wf.get("doc_comments"),
                    "attributes": wf.get("attributes"),
                }
            local[fname] = {
                "function_name": fname,
                "src_loc": fn.get("src_location"),
                "stringified_code": fn.get("src_code"),
                "line_number_start": fn.get("line_number_start", -1),
                "line_number_end":   fn.get("line_number_end",   -1),
                "functions_called":  self._ensure_type_in_calls(
                    (fn.get("functions_called", []) or [])   # free functions & macros
                    + (fn.get("methods_called",  []) or [])  # methods on a receiver
                ),
                "where_functions":   rust_where,
                "_type":             "_function",
                "fully_qualified_path": fn.get("fully_qualified_path"),
                # carry top-level Rust extras so we can map them in get_functions()
                "is_method": fn.get("is_method"),
                "self_type": fn.get("self_type"),
                "input_types": fn.get("input_types"),
                "output_types": fn.get("output_types"),
                "types_used": fn.get("types_used"),
                "literals_used": fn.get("literals_used"),
                "methods_called_meta": fn.get("methods_called"),  # keep if you want
                "visibility": fn.get("visibility"),
                "doc_comments": fn.get("doc_comments"),
                "attributes": fn.get("attributes"),
                "crate_name": fn.get("crate_name"),
                "module_path": fn.get("module_path"),
            }
        return local

    def _deduplicate_functions_called(self, local_fdep: Dict) -> None:
        """
        Remove duplicate function calls from each function.

        Args:
            local_fdep: Local function dependency dictionary
        """
        # rust entries already contain unique FQ paths – no need to dedup
        if any(v.get("fully_qualified_path") for v in local_fdep.values()):
            return

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
                    instances_used=function_body.get("instances_used",[]),
                    # --- Rust extras (safe no-ops for Haskell) ---
                    fully_qualified_path=function_body.get("fully_qualified_path"),
                    is_method=function_body.get("is_method"),
                    self_type=function_body.get("self_type"),
                    input_types=function_body.get("input_types"),
                    output_types=function_body.get("output_types"),
                    types_used=function_body.get("types_used"),
                    literals_used=function_body.get("literals_used"),
                    # keep methods_called (the *metadata* list) distinct from `functions_called`
                    methods_called=function_body.get("methods_called_meta"),
                    visibility=function_body.get("visibility"),
                    doc_comments=function_body.get("doc_comments"),
                    attributes=function_body.get("attributes"),
                    crate_name=function_body.get("crate_name"),
                    module_path=function_body.get("module_path"),
                )

                functions.append(function)

        return functions
