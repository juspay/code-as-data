# Code-as-Data MCP Server

This MCP (Model Context Protocol) server provides intelligent code analysis capabilities by leveraging the structured code data from the code-as-data system. It uses Qdrant for vector storage and Azure OpenAI for embeddings and code analysis.

## Features

The MCP server provides tools and resources for:

1. **Intelligent Code Search & Navigation**
   - Semantic code search based on natural language queries
   - Code navigation based on dependencies and relationships
   - Finding usage examples of code elements

2. **Domain Knowledge Extraction**
   - Extracting domain concepts from code
   - Generating domain models
   - Understanding business logic encoded in the codebase

3. **Code Review Assistance**
   - Analyzing code quality
   - Detecting code patterns
   - Suggesting improvements

4. **Performance Optimization**
   - Identifying performance hotspots
   - Analyzing algorithm complexity
   - Suggesting optimization opportunities

## Setup

### Prerequisites

- Python 3.8+
- PostgreSQL database with code-as-data schema
- Qdrant vector database
- Azure OpenAI API access

### Installation

1. Clone the repository and navigate to the MCP directory:

```bash
cd mcp
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file based on `.env.example` and fill in your configuration:

```bash
cp .env.example .env
# Edit .env with your configuration
```

### Data Processing

1. Set up Qdrant collections:

```bash
python setup_qdrant.py
```

2. Process and ingest data from the code-as-data database:

```bash
python data_processor.py
```

This will:
- Extract data from the PostgreSQL database
- Generate embeddings using Azure OpenAI
- Analyze code for domain knowledge, quality, and performance
- Store the processed data in Qdrant

### Running the Server

Start the MCP server:

```bash
python server.py
```

The server will be available at http://localhost:5000.

## MCP Tools

The server provides the following MCP tools:

### 1. semantic_code_search

Search for code based on semantic meaning rather than just text matching.

**Parameters:**
- `query` (string): The search query in natural language
- `filters` (object, optional): Filters to apply to the search
- `k` (integer, optional): Number of results to return (default: 5)

### 2. code_navigation

Navigate code based on relationships between elements.

**Parameters:**
- `element_id` (string): ID of the starting element
- `navigation_type` (string, optional): Type of navigation (dependencies, callers, related)
- `depth` (integer, optional): Depth of navigation (default: 1)

### 3. find_usage_examples

Find examples of how a code element is used throughout the codebase.

**Parameters:**
- `element_name` (string): Name of the element
- `element_type` (string): Type of the element (function, type, class)
- `module` (string, optional): Module to search in
- `limit` (integer, optional): Maximum number of examples to return (default: 5)

### 4. extract_domain_concepts

Extract domain concepts from the codebase.

**Parameters:**
- `modules` (array, optional): List of modules to analyze

### 5. generate_domain_model

Generate a domain model from the codebase.

**Parameters:**
- `modules` (array, optional): List of modules to analyze

### 6. analyze_code_quality

Analyze code quality and suggest improvements.

**Parameters:**
- `code` (string): Code to analyze
- `context` (object, optional): Context information

### 7. detect_code_patterns

Detect common code patterns in the codebase.

**Parameters:**
- `module` (string, optional): Module to analyze
- `pattern_type` (string, optional): Type of pattern to detect

### 8. identify_performance_hotspots

Identify performance hotspots in the codebase.

**Parameters:**
- `module` (string, optional): Module to analyze
- `threshold` (integer, optional): Complexity threshold for hotspots (default: 7)

### 9. analyze_algorithm_complexity

Analyze the complexity of an algorithm.

**Parameters:**
- `function_id` (string): ID of the function to analyze

## MCP Resources

The server provides the following MCP resources:

### 1. code_structure

Access to the code structure.

**Parameters:**
- `path` (string, optional): Path within the code structure

### 2. domain_knowledge

Access to domain knowledge.

**Parameters:**
- `concept` (string, optional): Domain concept to access

### 3. performance_metrics

Access to performance metrics.

**Parameters:**
- `module` (string, optional): Module to get metrics for
- `function` (string, optional): Function to get metrics for

## Architecture

The MCP server architecture consists of:

1. **Data Extraction Layer**: Extracts data from the code-as-data PostgreSQL database
2. **Azure OpenAI Integration**: Generates embeddings and performs code analysis
3. **Qdrant Vector Database**: Stores and retrieves vector embeddings for semantic search
4. **Flask API Server**: Exposes MCP tools and resources

## Customization

You can customize the server by:

1. Modifying the prompts in `analyze_code_with_llm` function to improve code analysis
2. Adding new tools and resources to the MCP server
3. Adjusting the complexity calculation in `calculate_complexity` function
4. Changing the embedding models in Azure OpenAI

## Troubleshooting

- If you encounter memory issues during data processing, try processing fewer modules at a time
- If embeddings fail, check your Azure OpenAI API key and endpoint
- If Qdrant connections fail, ensure Qdrant is running and accessible
- If database connections fail, check your PostgreSQL credentials and connection string
