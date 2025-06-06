import os
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from openai import AzureOpenAI
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize clients
qdrant_client = QdrantClient(
    host=os.getenv("QDRANT_HOST", "localhost"),
    port=int(os.getenv("QDRANT_PORT", 6333))
)

openai_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
)

# Database connection
db_url = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
engine = create_engine(db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Helper functions for embeddings and analysis
def generate_semantic_embedding(text):
    """Generate embeddings for text using Azure OpenAI."""
    response = openai_client.embeddings.create(
        model=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"),
        input=text
    )
    return response.data[0].embedding

def generate_code_embedding(code_text):
    """Generate embeddings for code using Azure OpenAI."""
    response = openai_client.embeddings.create(
        model=os.getenv("AZURE_OPENAI_CODE_EMBEDDING_DEPLOYMENT", "code-embedding-ada-002"),
        input=code_text
    )
    return response.data[0].embedding

def analyze_code_with_llm(code_text, analysis_type="general"):
    """Analyze code using Azure OpenAI."""
    # Customize prompt based on analysis type
    if analysis_type == "performance":
        prompt = f"""
        Analyze the following code for performance characteristics:
        
        ```
        {code_text}
        ```
        
        Provide a detailed performance analysis including:
        1. Time complexity (Big O notation)
        2. Space complexity
        3. Potential performance bottlenecks
        4. Optimization opportunities
        
        Format your response as a structured analysis with specific recommendations.
        """
    elif analysis_type == "domain":
        prompt = f"""
        Extract domain concepts and business logic from the following code:
        
        ```
        {code_text}
        ```
        
        Identify:
        1. Main domain entities
        2. Business concepts
        3. Relationships between entities
        4. Business rules encoded in the functions
        5. Domain-specific terminology
        
        Format your response as a structured list of domain concepts with brief descriptions.
        """
    elif analysis_type == "quality":
        prompt = f"""
        Analyze the following code for quality issues and suggest improvements:
        
        ```
        {code_text}
        ```
        
        Provide a detailed analysis including:
        1. Code quality issues
        2. Best practices violations
        3. Readability concerns
        4. Maintainability issues
        5. Specific improvement suggestions
        
        Format your response as a structured analysis with specific recommendations.
        """
    else:  # general analysis
        prompt = f"""
        Analyze the following code and provide a comprehensive summary:
        
        ```
        {code_text}
        ```
        
        Include:
        1. Main functionality
        2. Key components
        3. Important patterns or algorithms
        4. Potential issues or considerations
        
        Format your response as a structured analysis.
        """
    
    response = openai_client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_COMPLETION_DEPLOYMENT", "gpt-4"),
        messages=[
            {"role": "system", "content": "You are a code analysis assistant that provides detailed technical analysis."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=1000
    )
    
    return response.choices[0].message.content

def extract_function_calls(content):
    """Extract function calls from content using Azure OpenAI."""
    prompt = f"""
    Extract all function calls from the following code content:
    
    {content}
    
    Return only a list of function names that are being called, one per line.
    """
    
    response = openai_client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_COMPLETION_DEPLOYMENT", "gpt-4"),
        messages=[
            {"role": "system", "content": "You are a code analysis assistant that extracts function calls from code."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=500
    )
    
    function_calls = response.choices[0].message.content.strip().split("\n")
    return [call.strip() for call in function_calls if call.strip()]

# 1. Intelligent Code Search & Navigation

@app.route('/api/semantic_code_search', methods=['POST'])
def semantic_code_search():
    """
    Search for code based on semantic meaning rather than just text matching.
    """
    data = request.json
    query = data.get('query')
    filters = data.get('filters', {})
    k = data.get('k', 5)
    
    # Generate embedding for query
    query_embedding = generate_semantic_embedding(query)
    
    # Build filter expression
    filter_conditions = []
    if filters:
        for key, value in filters.items():
            if key in ["type", "module", "name"]:
                filter_conditions.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        match=qdrant_models.MatchValue(value=value)
                    )
                )
    
    # Perform vector search
    search_result = qdrant_client.search(
        collection_name="code_elements",
        query_vector=("semantic_vector", query_embedding),
        query_filter=qdrant_models.Filter(
            must=filter_conditions
        ) if filter_conditions else None,
        limit=k
    )
    
    # Process results
    results = []
    for scored_point in search_result:
        results.append({
            "id": scored_point.id,
            "content": scored_point.payload.get("content"),
            "type": scored_point.payload.get("type"),
            "name": scored_point.payload.get("name"),
            "module": scored_point.payload.get("module"),
            "score": scored_point.score
        })
    
    return jsonify({"results": results})

@app.route('/api/code_navigation', methods=['POST'])
def code_navigation():
    """
    Navigate code based on relationships between elements.
    """
    data = request.json
    element_id = data.get('element_id')
    navigation_type = data.get('navigation_type', 'dependencies')
    depth = data.get('depth', 1)
    
    # Get the element
    element = qdrant_client.retrieve(
        collection_name="code_elements",
        ids=[element_id]
    )
    
    if not element:
        return jsonify({"error": "Element not found"})
    
    element = element[0]
    
    # Get related elements based on navigation type
    related_elements = []
    
    if navigation_type == "dependencies":
        # Find elements that this element depends on
        # This would require additional logic to extract dependencies from the content
        # For simplicity, we'll use a semantic search approach
        
        # Extract function calls from the content
        function_calls = extract_function_calls(element.payload.get("content"))
        
        for call in function_calls:
            # Search for the called function
            search_result = qdrant_client.search(
                collection_name="code_elements",
                query_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="type",
                            match=qdrant_models.MatchValue(value="function")
                        ),
                        qdrant_models.FieldCondition(
                            key="name",
                            match=qdrant_models.MatchValue(value=call)
                        )
                    ]
                ),
                limit=1
            )
            
            if search_result:
                related_elements.append({
                    "id": search_result[0].id,
                    "name": search_result[0].payload.get("name"),
                    "type": search_result[0].payload.get("type"),
                    "module": search_result[0].payload.get("module"),
                    "relationship": "called_by"
                })
    
    elif navigation_type == "callers":
        # Find elements that call this element
        # This would require a more complex query or pre-computed relationships
        # For demonstration, we'll use a simplified approach
        
        element_name = element.payload.get("name")
        
        # Search for elements that might call this function
        search_result = qdrant_client.search(
            collection_name="code_elements",
            query_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="type",
                        match=qdrant_models.MatchValue(value="function")
                    )
                ]
            ),
            limit=100
        )
        
        for result in search_result:
            content = result.payload.get("content", "")
            if element_name in content:
                related_elements.append({
                    "id": result.id,
                    "name": result.payload.get("name"),
                    "type": result.payload.get("type"),
                    "module": result.payload.get("module"),
                    "relationship": "calls"
                })
    
    return jsonify({
        "element": {
            "id": element.id,
            "name": element.payload.get("name"),
            "type": element.payload.get("type"),
            "module": element.payload.get("module")
        },
        "related_elements": related_elements
    })

@app.route('/api/find_usage_examples', methods=['POST'])
def find_usage_examples():
    """
    Find examples of how a code element is used throughout the codebase.
    """
    data = request.json
    element_name = data.get('element_name')
    element_type = data.get('element_type')
    module = data.get('module')
    limit = data.get('limit', 5)
    
    # Build filter expression
    filter_conditions = []
    
    # Filter by type
    if element_type:
        filter_conditions.append(
            qdrant_models.FieldCondition(
                key="type",
                match=qdrant_models.MatchValue(value="function")  # We're looking for functions that use the element
            )
        )
    
    # Filter by module
    if module:
        filter_conditions.append(
            qdrant_models.FieldCondition(
                key="module",
                match=qdrant_models.MatchValue(value=module)
            )
        )
    
    # Search for usage examples
    search_result = qdrant_client.search(
        collection_name="code_elements",
        query_vector=("semantic_vector", generate_semantic_embedding(f"usage of {element_name}")),
        query_filter=qdrant_models.Filter(must=filter_conditions) if filter_conditions else None,
        limit=100  # Get more results to filter
    )
    
    # Filter results to find actual usage examples
    usage_examples = []
    for result in search_result:
        content = result.payload.get("content", "")
        if element_name in content:
            # Use LLM to extract the specific usage example
            prompt = f"""
            Extract the specific usage example of '{element_name}' from the following code:
            
            ```
            {content}
            ```
            
            Return only the relevant code snippet that shows how '{element_name}' is used.
            """
            
            usage_snippet = openai_client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_COMPLETION_DEPLOYMENT", "gpt-4"),
                messages=[
                    {"role": "system", "content": "You are a code analysis assistant that extracts usage examples."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            ).choices[0].message.content
            
            usage_examples.append({
                "id": result.id,
                "name": result.payload.get("name"),
                "type": result.payload.get("type"),
                "module": result.payload.get("module"),
                "usage_snippet": usage_snippet
            })
            
            if len(usage_examples) >= limit:
                break
    
    return jsonify({"usage_examples": usage_examples})

# 2. Domain Knowledge Extraction

@app.route('/api/extract_domain_concepts', methods=['POST'])
def extract_domain_concepts_api():
    """
    Extract domain concepts from the codebase.
    """
    data = request.json
    modules = data.get('modules')
    
    # Build filter expression for modules
    filter_conditions = []
    if modules:
        module_conditions = []
        for module in modules:
            module_conditions.append(
                qdrant_models.FieldCondition(
                    key="module",
                    match=qdrant_models.MatchValue(value=module)
                )
            )
        filter_conditions.append(qdrant_models.Filter(should=module_conditions))
    
    filter_conditions.append(
        qdrant_models.FieldCondition(
            key="type",
            match=qdrant_models.MatchValue(value="domain_knowledge")
        )
    )
    
    # Search for domain knowledge documents
    search_result = qdrant_client.search(
        collection_name="domain_knowledge",
        query_filter=qdrant_models.Filter(must=filter_conditions),
        limit=50
    )
    
    # Process results
    domain_concepts = []
    for result in search_result:
        domain_concepts.append({
            "module": result.payload.get("module"),
            "concepts": result.payload.get("content").replace(f"Domain Knowledge for Module: {result.payload.get('module')}\n\n", "")
        })
    
    return jsonify({"domain_concepts": domain_concepts})

@app.route('/api/generate_domain_model', methods=['POST'])
def generate_domain_model():
    """
    Generate a domain model from the codebase.
    """
    data = request.json
    modules = data.get('modules')
    
    # Get domain concepts first
    domain_concepts_response = extract_domain_concepts_api()
    domain_concepts = json.loads(domain_concepts_response.data)["domain_concepts"]
    
    # Use LLM to generate a domain model
    prompt = f"""
    Generate a comprehensive domain model based on the following domain concepts extracted from the codebase:
    
    {json.dumps(domain_concepts, indent=2)}
    
    Your domain model should include:
    1. Main entities and their attributes
    2. Relationships between entities
    3. Key business processes
    4. Business rules and constraints
    
    Format your response as a structured domain model with clear entity definitions and relationships.
    """
    
    domain_model = openai_client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_COMPLETION_DEPLOYMENT", "gpt-4"),
        messages=[
            {"role": "system", "content": "You are a domain modeling expert that can extract business models from code."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=2000
    ).choices[0].message.content
    
    return jsonify({"domain_model": domain_model})

# 3. Code Review Assistance

@app.route('/api/analyze_code_quality', methods=['POST'])
def analyze_code_quality_api():
    """
    Analyze code quality and suggest improvements.
    """
    data = request.json
    code = data.get('code')
    context = data.get('context', {})
    
    # Use Azure OpenAI to analyze code quality
    analysis = analyze_code_with_llm(code, "quality")
    
    return jsonify({"analysis": analysis})

@app.route('/api/detect_code_patterns', methods=['POST'])
def detect_code_patterns():
    """
    Detect common code patterns in the codebase.
    """
    data = request.json
    module = data.get('module')
    pattern_type = data.get('pattern_type')
    
    # Build filter expression
    filter_conditions = []
    
    if module:
        filter_conditions.append(
            qdrant_models.FieldCondition(
                key="module",
                match=qdrant_models.MatchValue(value=module)
            )
        )
    
    if pattern_type:
        filter_conditions.append(
            qdrant_models.FieldCondition(
                key="pattern_type",
                match=qdrant_models.MatchValue(value=pattern_type)
            )
        )
    
    # Search for code patterns
    search_result = qdrant_client.search(
        collection_name="code_review",
        query_filter=qdrant_models.Filter(must=filter_conditions) if filter_conditions else None,
        limit=20
    )
    
    # Process results
    patterns = []
    for result in search_result:
        if "pattern" in result.payload.get("type", ""):
            patterns.append({
                "id": result.id,
                "name": result.payload.get("name"),
                "type": result.payload.get("pattern_type"),
                "module": result.payload.get("module"),
                "description": result.payload.get("content")
            })
    
    return jsonify({"patterns": patterns})

# 4. Performance Optimization

@app.route('/api/identify_performance_hotspots', methods=['POST'])
def identify_performance_hotspots_api():
    """
    Identify performance hotspots in the codebase.
    """
    data = request.json
    module = data.get('module')
    threshold = data.get('threshold', 7)
    
    # Build filter expression
    filter_conditions = [
        qdrant_models.FieldCondition(
            key="type",
            match=qdrant_models.MatchValue(value="performance_analysis")
        )
    ]
    
    if module:
        filter_conditions.append(
            qdrant_models.FieldCondition(
                key="module",
                match=qdrant_models.MatchValue(value=module)
            )
        )
    
    # Search for performance hotspots
    search_result = qdrant_client.search(
        collection_name="performance",
        query_filter=qdrant_models.Filter(must=filter_conditions),
        limit=20
    )
    
    # Process results
    hotspots = []
    for result in search_result:
        complexity = result.payload.get("complexity", 0)
        if complexity >= threshold:
            hotspots.append({
                "id": result.id,
                "name": result.payload.get("function_name"),
                "module": result.payload.get("module"),
                "complexity": complexity,
                "dependency_count": result.payload.get("dependency_count"),
                "analysis": result.payload.get("content")
            })
    
    return jsonify({"hotspots": hotspots})

@app.route('/api/analyze_algorithm_complexity', methods=['POST'])
def analyze_algorithm_complexity():
    """
    Analyze the complexity of an algorithm.
    """
    data = request.json
    function_id = data.get('function_id')
    
    # Get the function
    function = qdrant_client.retrieve(
        collection_name="code_elements",
        ids=[function_id]
    )
    
    if not function:
        return jsonify({"error": "Function not found"})
    
    function = function[0]
    
    # Use Azure OpenAI to analyze algorithm complexity
    analysis = analyze_code_with_llm(function.payload.get("content"), "performance")
    
    return jsonify({"analysis": analysis})

# MCP Server metadata endpoint
@app.route('/mcp-info', methods=['GET'])
def mcp_info():
    """
    Return MCP server metadata.
    """
    return jsonify({
        "name": "code-analysis-mcp",
        "version": "1.0.0",
        "description": "MCP server for code analysis using Qdrant and Azure OpenAI",
        "tools": [
            {
                "name": "semantic_code_search",
                "description": "Search for code based on semantic meaning",
                "parameters": {
                    "query": {
                        "type": "string",
                        "description": "The search query in natural language"
                    },
                    "filters": {
                        "type": "object",
                        "description": "Filters to apply to the search",
                        "optional": True
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "optional": True,
                        "default": 5
                    }
                }
            },
            {
                "name": "code_navigation",
                "description": "Navigate code based on relationships",
                "parameters": {
                    "element_id": {
                        "type": "string",
                        "description": "ID of the starting element"
                    },
                    "navigation_type": {
                        "type": "string",
                        "description": "Type of navigation (dependencies, callers, related)",
                        "optional": True,
                        "default": "dependencies"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Depth of navigation",
                        "optional": True,
                        "default": 1
                    }
                }
            },
            {
                "name": "extract_domain_concepts",
                "description": "Extract domain concepts from the codebase",
                "parameters": {
                    "modules": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of modules to analyze",
                        "optional": True
                    }
                }
            },
            {
                "name": "analyze_code_quality",
                "description": "Analyze code quality and suggest improvements",
                "parameters": {
                    "code": {
                        "type": "string",
                        "description": "Code to analyze"
                    },
                    "context": {
                        "type": "object",
                        "description": "Context information",
                        "optional": True
                    }
                }
            },
            {
                "name": "identify_performance_hotspots",
                "description": "Identify performance hotspots in the codebase",
                "parameters": {
                    "module": {
                        "type": "string",
                        "description": "Module to analyze",
                        "optional": True
                    },
                    "threshold": {
                        "type": "integer",
                        "description": "Complexity threshold for hotspots",
                        "optional": True,
                        "default": 7
                    }
                }
            }
        ],
        "resources": [
            {
                "name": "code_structure",
                "description": "Access the code structure",
                "uriTemplate": "/api/code_structure{?path}",
                "parameters": {
                    "path": {
                        "type": "string",
                        "description": "Path within the code structure",
                        "optional": True
                    }
                }
            },
            {
                "name": "domain_knowledge",
                "description": "Access domain knowledge",
                "uriTemplate": "/api/domain_knowledge{?concept}",
                "parameters": {
                    "concept": {
                        "type": "string",
                        "description": "Domain concept to access",
                        "optional": True
                    }
                }
            },
            {
                "name": "performance_metrics",
                "description": "Access performance metrics",
                "uriTemplate": "/api/performance_metrics{?module,function}",
                "parameters": {
                    "module": {
                        "type": "string",
                        "description": "Module to get metrics for",
                        "optional": True
                    },
                    "function": {
                        "type": "string",
                        "description": "Function to get metrics for",
                        "optional": True
                    }
                }
            }
        ]
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
