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