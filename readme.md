# Code Analyzer Database

A Python application for processing code analysis dump files and storing them in PostgreSQL for querying and analysis.

## Overview

This project provides tools to:

1. Parse and process dump files containing code structure information
2. Insert the processed data into a PostgreSQL database
3. Query the database to analyze code structure and relationships

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL 12+

### Setup

1. Clone the repository:

```bash
git clone https://github.com/yourusername/code-as-data.git
cd code-as-data
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a PostgreSQL database:

```bash
createdb code_as_data
```

5. Create a `.env` file with your database connection details:

```
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432
DB_NAME=code_as_data
```

6. Set up the database schema:

```bash
python scripts/setup_db.py
```

## Usage

### Importing Dumps

To import dump files into the database:

```bash
python scripts/import_dumps.py /path/to/fdep_files /path/to/field_inspector_files
```

Options:
- `--clear`: Clear existing data in the database before importing

### Database Schema

The database schema includes the following main tables:

- `module`: Code modules
- `function`: Functions with their signatures and raw code
- `where_function`: Nested functions within parent functions
- `import`: Module imports
- `type`: Type definitions
- `constructor`: Type constructors
- `field`: Constructor fields
- `class`: Class definitions
- `instance`: Instance definitions
- `instance_function`: Associations between instances and functions

Relationships are maintained through foreign keys and association tables, allowing for complex queries about code structure and dependencies.

## Example Queries

Here are some example queries you can run using SQL or the QueryService:

### Find all functions in a module:

```python
from src.db.connection import SessionLocal
from src.services.query_service import QueryService

db = SessionLocal()
query_service = QueryService(db)

module = query_service.get_module_by_name("YourModuleName")
if module:
    functions = query_service.get_functions_by_module(module.id)
    for func in functions:
        print(f"{func.name}: {func.function_signature}")
```

### Find the most called functions:

```python
most_called = query_service.get_most_called_functions(limit=10)
for func in most_called:
    print(f"{func['name']} ({func['module']}): Called {func['calls']} times")
```

### Search for functions containing specific code:

```python
functions = query_service.search_function_by_content("specific code pattern")
for func in functions:
    print(f"{func.name} in {func.module.name}")
```

# Advanced Query Language

This document provides comprehensive documentation for the Advanced Query Language system implemented in the QueryService. The Advanced Query Language allows you to perform complex searches and analyses across your codebase using a structured JSON format.

## Table of Contents

1. [Introduction](#introduction)
2. [Query Structure](#query-structure)
3. [Basic Querying](#basic-querying)
4. [Advanced Filtering](#advanced-filtering)
5. [Query Operators](#query-operators)
6. [Join Operations](#join-operations)
7. [Nested Queries](#nested-queries)
8. [Pattern Matching](#pattern-matching)
9. [Code Analysis](#code-analysis)
10. [Examples](#examples)
    - [Finding Functions](#finding-functions)
    - [Module Analysis](#module-analysis)
    - [Type Analysis](#type-analysis)
    - [Dependency Analysis](#dependency-analysis)
    - [Similarity Analysis](#similarity-analysis)
    - [Complex Patterns](#complex-patterns)

## Introduction

The Advanced Query Language provides a flexible, JSON-based syntax for querying and analyzing code structures stored in the database. It supports complex operations like filtering, joining related entities, and identifying patterns across your codebase.

To use the Advanced Query Language, you'll create JSON-structured queries and pass them to the `execute_advanced_query()` method of the `QueryService` class.

## Query Structure

A basic query has the following structure:

```json
{
  "type": "<entity_type>",
  "conditions": [
    {"field": "<field_name>", "operator": "<operator>", "value": "<value>"}
  ],
  "joins": [
    {
      "type": "<related_entity_type>",
      "conditions": [
        {"field": "<field_name>", "operator": "<operator>", "value": "<value>"}
      ]
    }
  ]
}
```

Where:
- `type`: The primary entity type to query (e.g., "function", "module", "type")
- `conditions`: A list of filter conditions to apply to the main entity
- `joins`: A list of related entities to join with, each with their own conditions

## Basic Querying

### Querying a Single Entity Type

To query a single entity type with basic filtering:

```python
query = {
    "type": "function",
    "conditions": [
        {"field": "name", "operator": "eq", "value": "process_single_module"}
    ]
}

results = query_service.execute_advanced_query(query)
```

### Getting All Entities of a Type

To get all entities of a particular type:

```python
query = {
    "type": "module",
    "conditions": []
}

all_modules = query_service.execute_advanced_query(query)
```

## Advanced Filtering

### Multiple Conditions

You can specify multiple conditions on a single entity:

```python
query = {
    "type": "function",
    "conditions": [
        {"field": "name", "operator": "like", "value": "%parse%"},
        {"field": "line_number_start", "operator": "gt", "value": 100}
    ]
}
```

### Complex Value Types

Some operators support complex value types:

```python
# Range query with between operator
query = {
    "type": "function",
    "conditions": [
        {"field": "line_number_start", "operator": "between", "value": [100, 200]}
    ]
}

# List query with in operator
query = {
    "type": "function",
    "conditions": [
        {"field": "name", "operator": "in", "value": ["process", "parse", "load"]}
    ]
}
```

## Query Operators

The Advanced Query Language supports the following operators:

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal to | `{"field": "name", "operator": "eq", "value": "process"}` |
| `ne` | Not equal to | `{"field": "name", "operator": "ne", "value": "process"}` |
| `gt` | Greater than | `{"field": "line_number", "operator": "gt", "value": 100}` |
| `lt` | Less than | `{"field": "line_number", "operator": "lt", "value": 100}` |
| `ge` | Greater than or equal | `{"field": "line_number", "operator": "ge", "value": 100}` |
| `le` | Less than or equal | `{"field": "line_number", "operator": "le", "value": 100}` |
| `like` | SQL LIKE pattern | `{"field": "name", "operator": "like", "value": "%parse%"}` |
| `ilike` | Case-insensitive LIKE | `{"field": "name", "operator": "ilike", "value": "%parse%"}` |
| `in` | In a list of values | `{"field": "name", "operator": "in", "value": ["a", "b"]}` |
| `not_in` | Not in a list | `{"field": "name", "operator": "not_in", "value": ["a", "b"]}` |
| `contains` | Contains a substring | `{"field": "raw_string", "operator": "contains", "value": "error"}` |
| `startswith` | Starts with a string | `{"field": "name", "operator": "startswith", "value": "get_"}` |
| `endswith` | Ends with a string | `{"field": "name", "operator": "endswith", "value": "_parser"}` |
| `between` | Between two values | `{"field": "line_number", "operator": "between", "value": [100, 200]}` |
| `is_null` | Is null (or is not null) | `{"field": "function_signature", "operator": "is_null", "value": true}` |

## Join Operations

Joins allow you to query related entities based on their relationships.

### Simple Join

To query functions in a specific module:

```python
query = {
    "type": "function",
    "conditions": [],
    "joins": [
        {
            "type": "module",
            "conditions": [
                {"field": "name", "operator": "eq", "value": "import_parser"}
            ]
        }
    ]
}
```

### Multiple Joins

You can join multiple entity types:

```python
query = {
    "type": "function",
    "conditions": [
        {"field": "name", "operator": "like", "value": "%process%"}
    ],
    "joins": [
        {
            "type": "module",
            "conditions": [
                {"field": "name", "operator": "eq", "value": "import_parser"}
            ]
        },
        {
            "type": "called_function",
            "conditions": [
                {"field": "name", "operator": "eq", "value": "error_trace"}
            ]
        }
    ]
}
```

## Nested Queries

You can create nested queries by adding joins within joins:

```python
query = {
    "type": "module",
    "conditions": [
        {"field": "name", "operator": "eq", "value": "import_parser"}
    ],
    "joins": [
        {
            "type": "function",
            "conditions": [],
            "joins": [
                {
                    "type": "called_function",
                    "conditions": [
                        {"field": "name", "operator": "eq", "value": "error_trace"}
                    ]
                }
            ]
        }
    ]
}
```

## Pattern Matching

The system supports advanced pattern matching through specialized methods.

### Function Call Patterns

Find functions that call specific other functions:

```python
pattern = {
    "type": "function_call",
    "caller": "process",
    "callee": "error_trace"
}

results = query_service.pattern_match(pattern)
```

### Type Usage Patterns

Find where specific types are used:

```python
pattern = {
    "type": "type_usage",
    "type_name": "Function",
    "usage_in": "function"
}

results = query_service.pattern_match(pattern)
```

### Code Structure Patterns

Find specific code structures like nested functions:

```python
pattern = {
    "type": "code_structure",
    "structure_type": "nested_function"
}

results = query_service.pattern_match(pattern)
```

## Code Analysis

The system provides several specialized methods for more advanced code analysis:

### Finding Similar Functions

```python
similar_functions = query_service.find_similar_functions(function_id=123, threshold=0.7)
```

### Finding Code Patterns

```python
code_snippet = """
if error:
    error_trace(e)
    return None
"""

matches = query_service.find_code_patterns(pattern_code=code_snippet, min_matches=3)
```

### Grouping Similar Functions

```python
function_groups = query_service.group_similar_functions(similarity_threshold=0.8)
```

### Analyzing Module Coupling

```python
coupling_metrics = query_service.analyze_module_coupling()
```

### Finding Complex Functions

```python
complex_functions = query_service.find_complex_functions(complexity_threshold=15)
```

## Examples

### Finding Functions

**Find all functions with "parse" in their name:**

```python
query = {
    "type": "function",
    "conditions": [
        {"field": "name", "operator": "like", "value": "%parse%"}
    ]
}
```

**Find functions with more than 100 lines of code:**

```python
query = {
    "type": "function",
    "conditions": [
        {"field": "line_number_end", "operator": "gt", "value": 100},
        {"field": "line_number_start", "operator": "lt", "value": 100}
    ]
}
```

**Find functions that take a specific parameter type:**

```python
query = {
    "type": "function",
    "conditions": [
        {"field": "function_signature", "operator": "like", "value": "%Session%"}
    ]
}
```

**Find functions without a proper signature:**

```python
query = {
    "type": "function",
    "conditions": [
        {"field": "function_signature", "operator": "is_null", "value": true}
    ]
}
```

### Module Analysis

**Find modules with the most functions:**

```python
# First, query the modules and count their functions
modules = query_service.get_all_modules()

module_counts = []
for module in modules:
    functions = query_service.get_functions_by_module(module.id)
    module_counts.append({
        "module": module.name,
        "function_count": len(functions)
    })

# Sort by function count
module_counts.sort(key=lambda x: x["function_count"], reverse=True)
```

**Find modules with specific import patterns:**

```python
query = {
    "type": "module",
    "conditions": [],
    "joins": [
        {
            "type": "import",
            "conditions": [
                {"field": "module_name", "operator": "like", "value": "%sqlalchemy%"}
            ]
        }
    ]
}
```

### Type Analysis

**Find all data types:**

```python
query = {
    "type": "type",
    "conditions": [
        {"field": "type_of_type", "operator": "eq", "value": "DATA"}
    ]
}
```

**Find types with specific constructors:**

```python
query = {
    "type": "type",
    "conditions": [],
    "joins": [
        {
            "type": "constructor",
            "conditions": [
                {"field": "name", "operator": "eq", "value": "Module"}
            ]
        }
    ]
}
```

**Find all types used in a specific module:**

```python
query = {
    "type": "type",
    "conditions": [],
    "joins": [
        {
            "type": "module",
            "conditions": [
                {"field": "name", "operator": "eq", "value": "models"}
            ]
        }
    ]
}
```

### Dependency Analysis

**Find all functions that call a specific function:**

```python
# Using the pattern matching API
pattern = {
    "type": "function_call",
    "callee": "error_trace"
}

callers = query_service.pattern_match(pattern)
```

**Find modules with circular dependencies:**

```python
# Get all cross-module dependencies
dependencies = query_service.find_cross_module_dependencies()

# Find potential circular dependencies
circular_dependencies = []
module_deps = {}

for dep in dependencies:
    caller = dep["caller_module"]["name"]
    callee = dep["callee_module"]["name"]
    
    if caller not in module_deps:
        module_deps[caller] = set()
    module_deps[caller].add(callee)

# Check for circular dependencies (simplified approach)
for module, deps in module_deps.items():
    for dep in deps:
        if dep in module_deps and module in module_deps[dep]:
            circular_dependencies.append((module, dep))
```

### Similarity Analysis

**Find functions similar to a reference function:**

```python
similar_functions = query_service.find_similar_functions(function_id=123, threshold=0.7)
```

**Group similar functions:**

```python
function_groups = query_service.group_similar_functions(similarity_threshold=0.8)
```

**Find duplicated code patterns:**

```python
# Get all functions
query = {
    "type": "function",
    "conditions": []
}
functions = query_service.execute_advanced_query(query)

# Find similar implementation patterns across functions
patterns = {}
for function in functions:
    if not function.raw_string:
        continue
        
    lines = function.raw_string.strip().split('\n')
    for i in range(len(lines) - 4):  # Look for patterns of at least 5 lines
        pattern = '\n'.join(lines[i:i+5])
        if pattern not in patterns:
            patterns[pattern] = []
        patterns[pattern].append(function.name)

# Filter patterns that appear in multiple functions
duplicated_patterns = {
    pattern: funcs for pattern, funcs in patterns.items() 
    if len(funcs) > 1 and len(pattern.strip()) > 50  # Non-trivial patterns
}
```

### Complex Patterns

**Find error handling patterns:**

```python
error_pattern = """
try:
    # Some code
except Exception as e:
    error_trace(e)
"""

error_handling_functions = query_service.find_code_patterns(
    pattern_code=error_pattern, 
    min_matches=3
)
```

**Find complex functions that need refactoring:**

```python
complex_functions = query_service.find_complex_functions(complexity_threshold=15)
```

**Find modules with high coupling:**

```python
coupling_metrics = query_service.analyze_module_coupling()

# Get the most highly coupled modules
most_coupled = sorted(
    coupling_metrics["module_metrics"], 
    key=lambda x: x["total"], 
    reverse=True
)[:5]
```

**Find frequently used patterns that could be abstracted:**

```python
# First find common code patterns across functions
common_patterns = query_service.find_code_patterns(
    # A common pattern you've identified
    pattern_code="if not module_name:\n    return None", 
    min_matches=3
)

# These patterns might be candidates for abstraction into helper functions
```

**Find functions that operate on the same data structures:**

```python
query = {
    "type": "function",
    "conditions": [
        {"field": "function_signature", "operator": "like", "value": "%Repository%"}
    ]
}

repository_functions = query_service.execute_advanced_query(query)
```

These examples demonstrate the wide range of analyses possible with the Advanced Query Language. By combining different query types, joins, and specialized analysis methods, you can gain deep insights into your codebase structure and identify opportunities for improvement.

## Project Structure

- `src/`: Main source code
  - `db/`: Database models and connection handling
  - `models/`: Domain models representing code entities
  - `parsers/`: Parsers for different types of dump files
  - `services/`: Services for data processing and querying
- `scripts/`: Utility scripts for setup and importing
- `requirements.txt`: Project dependencies

## License

[MIT License](LICENSE)