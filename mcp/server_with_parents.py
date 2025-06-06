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
    include_parents = data.get('include_parents', False)
    include_children = data.get('include_children', False)
    
    # Generate embedding for query
    query_embedding = generate_semantic_embedding(query)
    
    # Build filter expression
    filter_conditions = []
    if filters:
        for key, value in filters.items():
            if key in ["type", "module", "name", "parent", "parent_type"]:
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
        result = {
            "id": scored_point.id,
            "content": scored_point.payload.get("content"),
            "type": scored_point.payload.get("type"),
            "name": scored_point.payload.get("name"),
            "module": scored_point.payload.get("module"),
            "score": scored_point.score,
            "parent": scored_point.payload.get("parent"),
            "parent_type": scored_point.payload.get("parent_type")
        }
        
        # Include parent information if requested
        if include_parents and scored_point.payload.get("parent"):
            parent = qdrant_client.retrieve(
                collection_name="code_elements",
                ids=[scored_point.payload.get("parent")]
            )
            if parent:
                result["parent_info"] = {
                    "id": parent[0].id,
                    "name": parent[0].payload.get("name"),
                    "type": parent[0].payload.get("type"),
                    "module": parent[0].payload.get("module")
                }
        
        # Include children information if requested
        if include_children:
            children = qdrant_client.search(
                collection_name="code_elements",
                query_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="parent",
                            match=qdrant_models.MatchValue(value=scored_point.id)
                        )
                    ]
                ),
                limit=10
            )
            if children:
                result["children"] = [
                    {
                        "id": child.id,
                        "name": child.payload.get("name"),
                        "type": child.payload.get("type"),
                        "module": child.payload.get("module")
                    } for child in children
                ]
        
        results.append(result)
    
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
    include_parents = data.get('include_parents', False)
    
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
                related_element = {
                    "id": search_result[0].id,
                    "name": search_result[0].payload.get("name"),
                    "type": search_result[0].payload.get("type"),
                    "module": search_result[0].payload.get("module"),
                    "relationship": "called_by",
                    "parent": search_result[0].payload.get("parent"),
                    "parent_type": search_result[0].payload.get("parent_type")
                }
                
                # Include parent information if requested
                if include_parents and search_result[0].payload.get("parent"):
                    parent = qdrant_client.retrieve(
                        collection_name="code_elements",
                        ids=[search_result[0].payload.get("parent")]
                    )
                    if parent:
                        related_element["parent_info"] = {
                            "id": parent[0].id,
                            "name": parent[0].payload.get("name"),
                            "type": parent[0].payload.get("type"),
                            "module": parent[0].payload.get("module")
                        }
                
                related_elements.append(related_element)
    
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
                related_element = {
                    "id": result.id,
                    "name": result.payload.get("name"),
                    "type": result.payload.get("type"),
                    "module": result.payload.get("module"),
                    "relationship": "calls",
                    "parent": result.payload.get("parent"),
                    "parent_type": result.payload.get("parent_type")
                }
                
                # Include parent information if requested
                if include_parents and result.payload.get("parent"):
                    parent = qdrant_client.retrieve(
                        collection_name="code_elements",
                        ids=[result.payload.get("parent")]
                    )
                    if parent:
                        related_element["parent_info"] = {
                            "id": parent[0].id,
                            "name": parent[0].payload.get("name"),
                            "type": parent[0].payload.get("type"),
                            "module": parent[0].payload.get("module")
                        }
                
                related_elements.append(related_element)
    
    elif navigation_type == "parent":
        # Get the parent of this element
        if element.payload.get("parent"):
            parent = qdrant_client.retrieve(
                collection_name="code_elements",
                ids=[element.payload.get("parent")]
            )
            if parent:
                related_elements.append({
                    "id": parent[0].id,
                    "name": parent[0].payload.get("name"),
                    "type": parent[0].payload.get("type"),
                    "module": parent[0].payload.get("module"),
                    "relationship": "parent_of",
                    "parent": parent[0].payload.get("parent"),
                    "parent_type": parent[0].payload.get("parent_type")
                })
    
    elif navigation_type == "children":
        # Get the children of this element
        children = qdrant_client.search(
            collection_name="code_elements",
            query_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="parent",
                        match=qdrant_models.MatchValue(value=element_id)
                    )
                ]
            ),
            limit=100
        )
        
        for child in children:
            related_elements.append({
                "id": child.id,
                "name": child.payload.get("name"),
                "type": child.payload.get("type"),
                "module": child.payload.get("module"),
                "relationship": "child_of",
                "parent": child.payload.get("parent"),
                "parent_type": child.payload.get("parent_type")
            })
    
    return jsonify({
        "element": {
            "id": element.id,
            "name": element.payload.get("name"),
            "type": element.payload.get("type"),
            "module": element.payload.get("module"),
            "parent": element.payload.get("parent"),
            "parent_type": element.payload.get("parent_type")
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
    include_context = data.get('include_context', True)
    
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
            
            usage_example = {
                "id": result.id,
                "name": result.payload.get("name"),
                "type": result.payload.get("type"),
                "module": result.payload.get("module"),
                "usage_snippet": usage_snippet,
                "parent": result.payload.get("parent"),
                "parent_type": result.payload.get("parent_type")
            }
            
            # Include context information if requested
            if include_context:
                # Get parent information
                if result.payload.get("parent"):
                    parent = qdrant_client.retrieve(
                        collection_name="code_elements",
                        ids=[result.payload.get("parent")]
                    )
                    if parent:
                        usage_example["parent_info"] = {
                            "id": parent[0].id,
                            "name": parent[0].payload.get("name"),
                            "type": parent[0].payload.get("type"),
                            "module": parent[0].payload.get("module")
                        }
            
            usage_examples.append(usage_example)
            
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
    include_context = data.get('include_context', True)
    
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
        domain_concept = {
            "module": result.payload.get("module"),
            "concepts": result.payload.get("content").replace(f"Domain Knowledge for Module: {result.payload.get('module')}\n\n", ""),
            "parent": result.payload.get("parent"),
            "parent_type": result.payload.get("parent_type")
        }
        
        # Include context information if requested
        if include_context and result.payload.get("parent"):
            parent = qdrant_client.retrieve(
                collection_name="code_elements",
                ids=[result.payload.get("parent")]
            )
            if parent:
                domain_concept["parent_info"] = {
                    "id": parent[0].id,
                    "name": parent[0].payload.get("name"),
                    "type": parent[0].payload.get("type"),
                    "module": parent[0].payload.get("module")
                }
        
        domain_concepts.append(domain_concept)
    
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
    include_context = data.get('include_context', True)
    
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
            pattern = {
                "id": result.id,
                "name": result.payload.get("name"),
                "type": result.payload.get("pattern_type"),
                "module": result.payload.get("module"),
                "description": result.payload.get("content"),
                "parent": result.payload.get("parent"),
                "parent_type": result.payload.get("parent_type")
            }
            
            # Include context information if requested
            if include_context and result.payload.get("parent"):
                parent = qdrant_client.retrieve(
                    collection_name="code_elements",
                    ids=[result.payload.get("parent")]
                )
                if parent:
                    pattern["parent_info"] = {
                        "id": parent[0].id,
                        "name": parent[0].payload.get("name"),
                        "type": parent[0].payload.get("type"),
                        "module": parent[0].payload.get("module")
                    }
            
            patterns.append(pattern)
    
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
    include_context = data.get('include_context', True)
    
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
            hotspot = {
                "id": result.id,
                "name": result.payload.get("function_name"),
                "module": result.payload.get("module"),
                "complexity": complexity,
                "dependency_count": result.payload.get("dependency_count"),
                "analysis": result.payload.get("content"),
                "parent": result.payload.get("parent"),
                "parent_type": result.payload.get("parent_type")
            }
            
            # Include context information if requested
            if include_context and result.payload.get("parent"):
                parent = qdrant_client.retrieve(
                    collection_name="code_elements",
                    ids=[result.payload.get("parent")]
                )
                if parent:
                    hotspot["parent_info"] = {
                        "id": parent[0].id,
                        "name": parent[0].payload.get("name"),
                        "type": parent[0].payload.get("type"),
                        "module": parent[0].payload.get("module")
                    }
            
            hotspots.append(hotspot)
    
    return jsonify({"hotspots": hotspots})

@app.route('/api/analyze_algorithm_complexity', methods=['POST'])
def analyze_algorithm_complexity():
    """
    Analyze the complexity of an algorithm.
    """
    data = request.json
    function_id = data.get('function_id')
    include_context = data.get('include_context', True)
    
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
    
    result = {
        "id": function.id,
        "name": function.payload.get("name"),
        "module": function.payload.get("module"),
        "analysis": analysis,
        "parent": function.payload.get("parent"),
        "parent_type": function.payload.get("parent_type")
    }
    
    # Include context information if requested
    if include_context and function.payload.get("parent"):
        parent = qdrant_client.retrieve(
            collection_name="code_elements",
            ids=[function.payload.get("parent")]
        )
        if parent:
            result["parent_info"] = {
                "id": parent[0].id,
                "name": parent[0].payload.get("name"),
                "type": parent[0].payload.get("type"),
                "module": parent[0].payload.get("module")
            }
    
    return jsonify({"analysis": result})

# 5. Hierarchical Code Navigation

@app.route('/api/get_code_hierarchy', methods=['POST'])
def get_code_hierarchy():
    """
    Get the hierarchical structure of code elements.
    """
    data = request.json
    root_id = data.get('root_id')  # If provided, start from this element
    module = data.get('module')    # If provided, get hierarchy for this module
    max_depth = data.get('max_depth', 3)
    
    if not root_id and not module:
        return jsonify({"error": "Either root_id or module must be provided"})
    
    # If module is provided but not root_id, find the module element
    if module and not root_id:
        module_elements = qdrant_client.search(
            collection_name="code_elements",
            query_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="type",
                        match=qdrant_models.MatchValue(value="module")
                    ),
                    qdrant_models.FieldCondition(
                        key="name",
                        match=qdrant_models.MatchValue(value=module)
                    )
                ]
            ),
            limit=1
        )
        
        if not module_elements:
            return jsonify({"error": f"Module '{module}' not found"})
        
        root_id = module_elements[0].id
    
    # Get the root element
    root_element = qdrant_client.retrieve(
        collection_name="code_elements",
        ids=[root_id]
    )
    
    if not root_element:
        return jsonify({"error": f"Element with ID '{root_id}' not found"})
    
    root_element = root_element[0]
    
    # Build the hierarchy recursively
    def build_hierarchy(element_id, current_depth=0):
        if current_depth >= max_depth:
            return {"id": element_id, "children": []}
        
        # Get the element
        element = qdrant_client.retrieve(
            collection_name="code_elements",
            ids=[element_id]
        )
        
        if not element:
            return None
        
        element = element[0]
        
        # Get children
        children = qdrant_client.search(
            collection_name="code_elements",
            query_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="parent",
                        match=qdrant_models.MatchValue(value=element_id)
                    )
                ]
            ),
            limit=100
        )
        
        # Build hierarchy node
        node = {
            "id": element.id,
            "name": element.payload.get("name"),
            "type": element.payload.get("type"),
            "module": element.payload.get("module"),
            "children": []
        }
        
        # Add children recursively
        for child in children:
            child_node = build_hierarchy(child.id, current_depth + 1)
            if child_node:
                node["children"].append(child_node)
        
        return node
    
    # Build the hierarchy starting from the root element
    hierarchy = build_hierarchy(root_id)
    
    return jsonify({"hierarchy": hierarchy})

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
                    },
                    "include_parents": {
                        "type": "boolean",
                        "description": "Whether to include parent information",
                        "optional": True,
                        "default": False
                    },
                    "include_children": {
                        "type": "boolean",
                        "description": "Whether to include children information",
                        "optional": True,
                        "default": False
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
                        "description": "Type of navigation (dependencies, callers, parent, children)",
                        "optional": True,
                        "default": "dependencies"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Depth of navigation",
                        "optional": True,
                        "default": 1
                    },
                    "include_parents": {
                        "type": "boolean",
                        "description": "Whether to include parent information",
                        "optional": True,
                        "default": False
                    }
                }
            },
            {
                "name": "find_usage_examples",
                "description": "Find examples of how a code element is used",
                "parameters": {
                    "element_name": {
                        "type": "string",
                        "description": "Name of the element"
                    },
                    "element_type": {
                        "type": "string",
                        "description": "Type of the element (function, type, class)",
                        "optional": True
                    },
                    "module": {
                        "type": "string",
                        "description": "Module to search in",
                        "optional": True
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of examples to return",
                        "optional": True,
                        "default": 5
                    },
                    "include_context": {
                        "type": "boolean",
                        "description": "Whether to include context information",
                        "optional": True,
                        "default": True
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
                    },
                    "include_context": {
                        "type": "boolean",
                        "description": "Whether to include context information",
                        "optional": True,
                        "default": True
                    }
                }
            },
            {
                "name": "generate_domain_model",
                "description": "Generate a domain model from the codebase",
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
                "name": "detect_code_patterns",
                "description": "Detect common code patterns in the codebase",
                "parameters": {
                    "module": {
                        "type": "string",
                        "description": "Module to analyze",
                        "optional": True
                    },
                    "pattern_type": {
                        "type": "string",
                        "description": "Type of pattern to detect",
                        "optional": True
                    },
                    "include_context": {
                        "type": "boolean",
                        "description": "Whether to include context information",
                        "optional": True,
                        "default": True
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
                    },
                    "include_context": {
                        "type": "boolean",
                        "description": "Whether to include context information",
                        "optional": True,
                        "default": True
                    }
                }
            },
            {
                "name": "analyze_algorithm_complexity",
                "description": "Analyze the complexity of an algorithm",
                "parameters": {
                    "function_id": {
                        "type": "string",
                        "description": "ID of the function to analyze"
                    },
                    "include_context": {
                        "type": "boolean",
                        "description": "Whether to include context information",
                        "optional": True,
                        "default": True
                    }
                }
            },
            {
                "name": "get_code_hierarchy",
                "description": "Get the hierarchical structure of code elements",
                "parameters": {
                    "root_id": {
                        "type": "string",
                        "description": "ID of the root element",
                        "optional": True
                    },
                    "module": {
                        "type": "string",
                        "description": "Module to get hierarchy for",
                        "optional": True
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth of the hierarchy",
                        "optional": True,
                        "default": 3
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
