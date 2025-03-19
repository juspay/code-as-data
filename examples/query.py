#!/usr/bin/env python3
"""
Example script demonstrating how to query the database.
"""
import os
import sys
import argparse
import json

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.connection import SessionLocal
from src.services.query_service import QueryService


def list_modules():
    """List all modules in the database."""
    db = SessionLocal()
    try:
        query_service = QueryService(db)
        modules = query_service.get_all_modules()

        print(f"Found {len(modules)} modules:")
        for module in modules:
            print(f"- {module.name} (ID: {module.id})")
    finally:
        db.close()


def module_details(module_name):
    """
    Show details for a specific module.

    Args:
        module_name: Name of the module
    """
    db = SessionLocal()
    try:
        query_service = QueryService(db)

        # Get module
        module = query_service.get_module_by_name(module_name)
        if not module:
            print(f"Module not found: {module_name}")
            return

        print(f"Module: {module.name} (ID: {module.id})")
        print(f"Path: {module.path}")

        # Get function count
        functions = query_service.get_functions_by_module(module.id)
        print(f"Functions: {len(functions)}")

        # Get type count
        types = query_service.get_types_by_module(module.id)
        print(f"Types: {len(types)}")

        # Get class count
        classes = query_service.get_classes_by_module(module.id)
        print(f"Classes: {len(classes)}")

        # Get import count
        imports = query_service.get_imports_by_module(module.id)
        print(f"Imports: {len(imports)}")

        # Get instance count
        instances = query_service.get_instances_by_module(module.id)
        print(f"Instances: {len(instances)}")
    finally:
        db.close()


def function_details(function_name, module_name=None):
    """
    Show details for a specific function.

    Args:
        function_name: Name of the function
        module_name: Optional module name filter
    """
    db = SessionLocal()
    try:
        query_service = QueryService(db)

        # Get module ID if module name is provided
        module_id = None
        if module_name:
            module = query_service.get_module_by_name(module_name)
            if not module:
                print(f"Module not found: {module_name}")
                return
            module_id = module.id

        # Get functions
        functions = query_service.get_function_by_name(function_name, module_id)

        if not functions:
            print(f"Function not found: {function_name}")
            return

        print(f"Found {len(functions)} matching functions:")

        for func in functions:
            print("\n" + "=" * 50)
            print(f"Function: {func.name} (ID: {func.id})")
            print(f"Module: {func.module.name}")
            print(f"Signature: {func.function_signature}")
            print(f"Source location: {func.src_loc}")

            # Get detailed information
            details = query_service.get_function_details(func.id)

            if details["where_functions"]:
                print("\nWhere functions:")
                for wf in details["where_functions"]:
                    print(f"- {wf['name']}: {wf['signature']}")

            if details["calls"]:
                print("\nCalls:")
                for call in details["calls"]:
                    print(f"- {call['name']} in {call['module']}")

            if details["called_by"]:
                print("\nCalled by:")
                for caller in details["called_by"]:
                    print(f"- {caller['name']} in {caller['module']}")

            print("\nRaw code:")
            print(func.raw_string)
    finally:
        db.close()


def type_details(type_name, module_name=None):
    """
    Show details for a specific type.

    Args:
        type_name: Name of the type
        module_name: Optional module name filter
    """
    db = SessionLocal()
    try:
        query_service = QueryService(db)

        # Get module ID if module name is provided
        module_id = None
        if module_name:
            module = query_service.get_module_by_name(module_name)
            if not module:
                print(f"Module not found: {module_name}")
                return
            module_id = module.id

        # Get types
        types = query_service.get_type_by_name(type_name, module_id)

        if not types:
            print(f"Type not found: {type_name}")
            return

        print(f"Found {len(types)} matching types:")

        for type_obj in types:
            print("\n" + "=" * 50)
            print(f"Type: {type_obj['name']} (ID: {type_obj['id']})")
            print(f"Module: {type_obj['module']}")
            print(f"Type of type: {type_obj['type_of_type']}")

            if type_obj["constructors"]:
                print("\nConstructors:")
                for constructor in type_obj["constructors"]:
                    print(f"\n- {constructor['name']}")

                    if constructor["fields"]:
                        print("  Fields:")
                        for field in constructor["fields"]:
                            print(f"  - {field['name']}: {field['type_raw']}")

            print("\nRaw code:")
            print(type_obj["raw_code"])
    finally:
        db.close()


def most_called_functions(limit=10):
    """
    Show the most called functions.

    Args:
        limit: Maximum number of results
    """
    db = SessionLocal()
    try:
        query_service = QueryService(db)
        functions = query_service.get_most_called_functions(limit)

        print(f"Top {limit} most called functions:")
        for i, func in enumerate(functions, 1):
            print(
                f"{i}. {func['name']} in {func['module']}: Called {func['calls']} times"
            )
    finally:
        db.close()


def function_call_graph(function_name, module_name, depth=2):
    """
    Show the call graph for a function.

    Args:
        function_name: Name of the function
        module_name: Name of the module
        depth: Maximum depth of the call graph
    """
    db = SessionLocal()
    try:
        query_service = QueryService(db)

        # Get module
        module = query_service.get_module_by_name(module_name)
        if not module:
            print(f"Module not found: {module_name}")
            return

        # Get function
        functions = query_service.get_function_by_name(function_name, module.id)
        if not functions:
            print(f"Function not found: {function_name} in {module_name}")
            return

        function = functions[0]

        # Get call graph
        graph = query_service.get_function_call_graph(function.id, depth)

        print(f"Call graph for {function_name} in {module_name} (depth {depth}):")
        print(json.dumps(graph, indent=2))
    finally:
        db.close()


def search_function(pattern):
    """
    Search for functions containing a specific pattern.

    Args:
        pattern: Pattern to search for
    """
    db = SessionLocal()
    try:
        query_service = QueryService(db)
        functions = query_service.search_function_by_content(pattern)

        print(f"Found {len(functions)} functions containing '{pattern}':")
        for func in functions:
            print(
                f"- {func.name} in {func.module.name if func.module else 'Unknown module'}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query the code analysis database")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List modules command
    list_parser = subparsers.add_parser("list-modules", help="List all modules")

    # Module details command
    module_parser = subparsers.add_parser("module", help="Show module details")
    module_parser.add_argument("name", help="Module name")

    # Function details command
    function_parser = subparsers.add_parser("function", help="Show function details")
    function_parser.add_argument("name", help="Function name")
    function_parser.add_argument("--module", help="Module name filter")

    # Type details command
    type_parser = subparsers.add_parser("type", help="Show type details")
    type_parser.add_argument("name", help="Type name")
    type_parser.add_argument("--module", help="Module name filter")

    # Most called functions command
    most_called_parser = subparsers.add_parser(
        "most-called", help="Show most called functions"
    )
    most_called_parser.add_argument(
        "--limit", type=int, default=10, help="Maximum number of results"
    )

    # Function call graph command
    call_graph_parser = subparsers.add_parser(
        "call-graph", help="Show function call graph"
    )
    call_graph_parser.add_argument("function", help="Function name")
    call_graph_parser.add_argument("module", help="Module name")
    call_graph_parser.add_argument(
        "--depth", type=int, default=2, help="Maximum depth of the call graph"
    )

    # Search function command
    search_parser = subparsers.add_parser("search", help="Search for functions")
    search_parser.add_argument("pattern", help="Pattern to search for")

    args = parser.parse_args()

    # Execute command
    if args.command == "list-modules":
        list_modules()
    elif args.command == "module":
        module_details(args.name)
    elif args.command == "function":
        function_details(args.name, args.module)
    elif args.command == "type":
        type_details(args.name, args.module)
    elif args.command == "most-called":
        most_called_functions(args.limit)
    elif args.command == "call-graph":
        function_call_graph(args.function, args.module, args.depth)
    elif args.command == "search":
        search_function(args.pattern)
    else:
        parser.print_help()
