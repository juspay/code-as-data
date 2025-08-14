import json
import concurrent.futures
from typing import Dict, List, Optional

from . import list_files_recursive, get_module_name, error_trace
from code_as_data.models.instance_model import Instance
from code_as_data.models.function_model import Function


class InstanceParser:
    """Parser for instance data from dump files."""

    def __init__(
        self,
        path: str,
        base_dir_path: str,
        module_vs_functions: Dict[str, List[Function]] = None,
    ):
        """
        Initialize the instance parser.

        Args:
            path: Path to the instance dump files
            base_dir_path: Base directory path
            module_vs_functions: Dictionary of modules to their functions
        """
        self.modules_vs_instances: Dict[str, List[Instance]] = {}
        self.module_vs_functions: Dict[str, List[Function]] = module_vs_functions or {}
        self.path = path
        self.base_dir_path = base_dir_path

    def update_dict_module_vs_instance(
        self, module_vs_functions: Dict[str, List[Function]]
    ) -> None:
        """
        Update the module vs functions dictionary.

        Args:
            module_vs_functions: Dictionary of modules to their functions
        """
        self.module_vs_functions = module_vs_functions

    def find_functions_by_line(
        self,
        start: int,
        end: int,
        module_name: str,
        module_functions: List[Function] = None,
    ) -> List[Function]:
        """
        Find functions within a line range.

        Args:
            start: Start line number
            end: End line number
            module_name: Name of the module
            module_functions: List of module functions (optional)

        Returns:
            List of functions within the line range
        """
        module_functions = (
            module_functions
            if module_functions
            else self.module_vs_functions.get(module_name, [])
        )

        functions_list = []
        for function in module_functions:
            if (
                function.line_number_start >= start
                and function.line_number_start <= end
            ):
                functions_list.append(function)

        return functions_list

    def process_single_module(self, path: str) -> List[Instance]:
        """
        Process a single module's instances.

        Args:
            path: Path to the instance file

        Returns:
            List of Instance objects
        """
        try:
            module_name = get_module_name(
                base_dir_path=self.base_dir_path,
                path=path,
                to_replace=".hs.instance_code.json",
            )

            with open(path, "r") as f:
                instances_list = json.load(f)

            self.modules_vs_instances[module_name] = []

            for i in instances_list:
                functions = self.find_functions_by_line(
                    i.get("line_number", [-1, -1])[0],
                    i.get("line_number", [-1, -1])[1],
                    module_name,
                    self.module_vs_functions.get(module_name, []),
                )

                i["line_number_start"] = i.get("line_number", [-1, -1])[0]
                i["line_number_end"] = i.get("line_number", [-1, -1])[1]
                i["functions"] = functions
                i["src_loc"] = i.get("instanceLocation", "")
                i["module_name"] = module_name

                def remove_qualified_prefixes(input_string):
                    """
                    Removes any qualified part (prefix followed by a dot) from words in a string.
                    
                    Examples:
                    - "API.TransactionSync" becomes "TransactionSync"
                    - "Package.SubPackage.Class" becomes "Class"
                    - "Namespace.Type" becomes "Type"
                    
                    Args:
                        input_string (str): The input string to process
                        
                    Returns:
                        str: The string with qualified prefixes removed
                    """
                    # Split the string into words
                    words = input_string.split()
                    
                    # Process each word to remove qualified prefixes
                    processed_words = []
                    for word in words:
                        # Take only the part after the last dot if any dots exist
                        if "." in word:
                            processed_words.append(word.split(".")[-1])
                        else:
                            processed_words.append(word)
                    
                    # Join the processed words back into a string
                    return " ".join(processed_words)

                i["instance_signature"] = (i.get("instanceType", ""))
                i["instance_id"] = remove_qualified_prefixes(i.get("instanceType", ""))


                self.modules_vs_instances[module_name].append(Instance(**i))

            return self.modules_vs_instances.get(module_name, [])

        except Exception as e:
            error_trace(e)
            return []

    def load_all_files(self) -> Dict[str, List[Instance]]:
        """
        Load all instance files.

        Returns:
            Dictionary of modules to their instances
        """
        files = list_files_recursive(self.path, pattern=".hs.instance_code.json")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
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

        return self.modules_vs_instances
