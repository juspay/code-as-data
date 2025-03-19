#!/usr/bin/env python3
"""
Script to import dump files into the database.
"""
import os
import sys
import argparse
import time

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.connection import SessionLocal
from src.services.dump_service import DumpService


def import_dumps(fdep_path: str, field_inspector_path: str, clear_db: bool = False):
    """
    Import dump files into the database.

    Args:
        fdep_path: Path to the fdep files
        field_inspector_path: Path to the field inspector files
        clear_db: Whether to clear the database before importing
    """
    # Validate paths
    if not os.path.exists(fdep_path):
        print(f"Error: Path not found: {fdep_path}")
        sys.exit(1)

    if not os.path.exists(field_inspector_path):
        print(f"Error: Path not found: {field_inspector_path}")
        sys.exit(1)

    # Initialize dump service
    dump_service = DumpService(fdep_path, field_inspector_path)

    # # Clear database if requested
    # if clear_db:
    #     print("Clearing existing data...")
    #     # Execute raw SQL to delete data while maintaining schema
    #     db.execute(
    #         "TRUNCATE TABLE module, function, where_function, import, type, constructor, "
    #         "field, class, instance, instance_function, function_dependency, type_dependency "
    #         "CASCADE"
    #     )
    #     db.commit()
    db = SessionLocal()
    # Clear database if requested
    if clear_db:
        print("Clearing existing data...")
        # Execute raw SQL to delete data while maintaining schema
        from sqlalchemy import text

        truncate_sql = text(
            "TRUNCATE TABLE module, function, where_function, import, type, constructor, "
            "field, class, instance, instance_function, function_dependency, type_dependency "
            "CASCADE"
        )
        db.execute(truncate_sql)
        db.commit()

    # Import dumps
    print("Importing dump files...")
    start_time = time.time()

    try:
        # Process and insert data
        dump_service.insert_data()

        elapsed_time = time.time() - start_time
        print(f"Import completed successfully in {elapsed_time:.2f} seconds.")
    except Exception as e:
        print(f"Error during import: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import dump files into the database")
    parser.add_argument("fdep_path", help="Path to the fdep files")
    parser.add_argument(
        "--clear", action="store_true", help="Clear the database before importing"
    )

    args = parser.parse_args()
    import_dumps(args.fdep_path, args.fdep_path, args.clear)
