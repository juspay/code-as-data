from typing import List
import os
from pathlib import Path


def list_files_recursive(path: str, pattern: str) -> List[str]:
    """
    List all files in a directory and its subdirectories that match a pattern.

    Args:
        path: Base directory path
        pattern: File pattern to match

    Returns:
        List of file paths
    """
    result = []
    for root, _, files in os.walk(path):
        for file in files:
            if pattern in file:
                result.append(os.path.join(root, file))
    return result


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


def replace_all(text, replacements):
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def get_module_name(base_dir_path, path, to_replace=""):
    path = Path(path).relative_to(base_dir_path)
    finals_parts = []
    pth_parts = path.parts
    cur = 0
    skip_single = {"app", "dist"}
    skip_pairs = {("build", "autogen")}
    while cur < len(pth_parts):
        if pth_parts[cur] in skip_single:
            cur += 1
            continue
        if cur + 1 < len(pth_parts) and (pth_parts[cur], pth_parts[cur+1]) in skip_pairs:
            cur += 2
            continue
        finals_parts.append(pth_parts[cur])
        cur += 1
    path = (
        "/".join(finals_parts)
        .replace(".hs.json", "")
        .replace(".hs.module_imports.json", "")
        .replace(".hs.type.typechecker.json", "")
        .replace(".hs.function_instance_mapping.json", "")
        .replace(".hs.function_code.json", "")
        .replace(".hs.types_code.json", "")
        .replace(".hs.class_code.json", "")
        .replace(".hs.instance_code.json", "")
        .replace(".hs.fieldUsage.json", "")
        .replace(".hs.typeUpdates.json", "")
        .replace(".hs.types.parser.json", "")
    )
    patterns = [
        ("src/", "src/"),
        ("src-generated/", "src-generated/"),
        ("src-extras/", "src-extras/"),
        ("/app/", "/app/"),
        ("test/", "test/"),
    ]
    for pattern, split_pattern in patterns:
        if pattern in path:
            path = path.split(split_pattern)[-1]
            break
    # path = Path(path).stem
    module_name = replace_all(path, [("/", ".")])
    # print(module_name, path)
    return module_name


def error_trace(error: Exception) -> None:
    """
    Print an error with traceback.

    Args:
        error: Exception to print
    """
    import traceback

    print(f"ERROR: {error}")
    traceback.print_exc()
