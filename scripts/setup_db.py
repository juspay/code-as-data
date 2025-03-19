#!/usr/bin/env python3
"""
Script to set up the database schema.
"""
import os
import sys
import argparse

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.connection import engine, Base
from src.db.models import (
    Module,
    Function,
    WhereFunction,
    Import,
    Type,
    Constructor,
    Field,
    Class,
    Instance,
    InstanceFunction,
    function_dependency,
    type_dependency,
)


def setup_database(drop_tables: bool = False):
    """
    Set up the database schema.

    Args:
        drop_tables: Whether to drop existing tables
    """
    if drop_tables:
        print("Dropping existing tables...")
        Base.metadata.drop_all(engine)

    print("Creating tables...")
    Base.metadata.create_all(engine)
    print("Database setup complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up the database schema")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before creating new ones",
    )

    args = parser.parse_args()
    setup_database(args.drop)
