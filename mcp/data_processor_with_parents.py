import os
import json
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from openai import AzureOpenAI
import time
import uuid
from tqdm import tqdm

# Load environment variables
load_dotenv()

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

def generate_semantic_embedding(text):
    """Generate embeddings for text using Azure OpenAI."""
    try:
        response = openai_client.embeddings.create(
            model=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"),
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating semantic embedding: {e}")
        # Return a zero vector as fallback
        return [0.0] * 1536

def generate_code_embedding(code_text):
    """Generate embeddings for code using Azure OpenAI."""
    try:
        response = openai_client.embeddings.create(
            model=os.getenv("AZURE_OPENAI_CODE_EMBEDDING_DEPLOYMENT", "code-embedding-ada-002"),
            input=code_text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating code embedding: {e}")
        # Return a zero vector as fallback
        return [0.0] * 1536

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
    
    try:
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
    except Exception as e:
        print(f"Error analyzing code with LLM: {e}")
        return "Error analyzing code."

def calculate_complexity(function_data):
    """Calculate a simple complexity score for a function."""
    complexity = 1  # Base complexity
    
    if not function_data.get("raw_string"):
        return complexity
    
    # Count decision points
    decision_keywords = ["if", "case", "of", "where", "let", "do", "->", "| "]
    for keyword in decision_keywords:
        complexity += function_data.get("raw_string", "").count(keyword)
    
    # Add complexity based on function length
    line_count = 0
    if function_data.get("line_number_start") and function_data.get("line_number_end"):
        line_count = function_data["line_number_end"] - function_data["line_number_start"]
        complexity += line_count // 10  # Add 1 for every 10 lines
    
    # Add complexity based on dependencies
    dependency_count = len(function_data.get("functions_called", []))
    complexity += dependency_count // 5  # Add 1 for every 5 dependencies
    
    return complexity

def extract_data_from_db():
    """Extract data from the code-as-data database."""
    db = SessionLocal()
    try:
        print("Extracting modules...")
        modules = db.execute(text("SELECT id, name, path FROM module")).fetchall()
        
        extracted_data = []
        
        for module in tqdm(modules, desc="Processing modules"):
            module_id, module_name, module_path = module
            
            module_data = {
                "id": f"module:{module_id}",
                "name": module_name,
                "path": module_path,
                "content": {}
            }
            
            # Get functions for this module
            functions = db.execute(
                text("""
                    SELECT id, name, function_signature, raw_string, src_loc, 
                           line_number_start, line_number_end, type_enum
                    FROM function
                    WHERE module_id = :module_id
                """),
                {"module_id": module_id}
            ).fetchall()
            
            module_data["content"]["functions"] = []
            
            for function in functions:
                function_id, name, signature, raw_string, src_loc, line_start, line_end, type_enum = function
                
                # Get function calls
                function_calls = db.execute(
                    text("""
                        SELECT fc.module_name, fc.name, fc.function_name, fc.package_name
                        FROM function_called fc
                        WHERE fc.function_id = :function_id
                    """),
                    {"function_id": function_id}
                ).fetchall()
                
                calls = []
                for call in function_calls:
                    call_module, call_name, call_function_name, call_package = call
                    calls.append({
                        "module_name": call_module,
                        "name": call_name or call_function_name,
                        "package_name": call_package
                    })
                
                # Get callers (functions that call this function)
                callers = db.execute(
                    text("""
                        SELECT f.id, f.name, m.name as module_name
                        FROM function f
                        JOIN function_dependency fd ON f.id = fd.caller_id
                        JOIN module m ON f.module_id = m.id
                        WHERE fd.callee_id = :function_id
                    """),
                    {"function_id": function_id}
                ).fetchall()
                
                called_by = []
                for caller in callers:
                    caller_id, caller_name, caller_module = caller
                    called_by.append({
                        "id": caller_id,
                        "name": caller_name,
                        "module": caller_module
                    })
                
                # Calculate complexity
                function_data = {
                    "id": function_id,
                    "function_name": name,
                    "raw_string": raw_string,
                    "line_number_start": line_start,
                    "line_number_end": line_end,
                    "functions_called": calls
                }
                complexity = calculate_complexity(function_data)
                
                function_data = {
                    "id": f"function:{function_id}",
                    "name": name,
                    "signature": signature,
                    "raw_string": raw_string,
                    "src_loc": src_loc,
                    "line_start": line_start,
                    "line_end": line_end,
                    "type_enum": type_enum,
                    "calls": calls,
                    "called_by": called_by,
                    "metrics": {
                        "complexity": complexity,
                        "dependency_count": len(calls),
                        "caller_count": len(called_by)
                    }
                }
                
                module_data["content"]["functions"].append(function_data)
            
            # Get types for this module
            types = db.execute(
                text("""
                    SELECT id, type_name, raw_code, src_loc, type_of_type, 
                           line_number_start, line_number_end
                    FROM type
                    WHERE module_id = :module_id
                """),
                {"module_id": module_id}
            ).fetchall()
            
            module_data["content"]["types"] = []
            
            for type_obj in types:
                type_id, type_name, raw_code, src_loc, type_of_type, line_start, line_end = type_obj
                
                # Get constructors for this type
                constructors = db.execute(
                    text("""
                        SELECT id, name
                        FROM constructor
                        WHERE type_id = :type_id
                    """),
                    {"type_id": type_id}
                ).fetchall()
                
                constructor_data = []
                
                for constructor in constructors:
                    constructor_id, constructor_name = constructor
                    
                    # Get fields for this constructor
                    fields = db.execute(
                        text("""
                            SELECT id, field_name, field_type_raw
                            FROM field
                            WHERE constructor_id = :constructor_id
                        """),
                        {"constructor_id": constructor_id}
                    ).fetchall()
                    
                    field_data = []
                    for field in fields:
                        field_id, field_name, field_type_raw = field
                        field_data.append({
                            "id": f"field:{field_id}",
                            "name": field_name,
                            "type": field_type_raw
                        })
                    
                    constructor_data.append({
                        "id": f"constructor:{constructor_id}",
                        "name": constructor_name,
                        "fields": field_data
                    })
                
                type_data = {
                    "id": f"type:{type_id}",
                    "name": type_name,
                    "raw_code": raw_code,
                    "src_loc": src_loc,
                    "type_of_type": type_of_type,
                    "line_start": line_start,
                    "line_end": line_end,
                    "constructors": constructor_data
                }
                
                module_data["content"]["types"].append(type_data)
            
            # Get classes for this module
            classes = db.execute(
                text("""
                    SELECT id, class_name, class_definition, src_location, 
                           line_number_start, line_number_end
                    FROM class
                    WHERE module_id = :module_id
                """),
                {"module_id": module_id}
            ).fetchall()
            
            module_data["content"]["classes"] = []
            
            for class_obj in classes:
                class_id, class_name, class_definition, src_location, line_start, line_end = class_obj
                
                class_data = {
                    "id": f"class:{class_id}",
                    "name": class_name,
                    "definition": class_definition,
                    "src_loc": src_location,
                    "line_start": line_start,
                    "line_end": line_end
                }
                
                module_data["content"]["classes"].append(class_data)
            
            # Get imports for this module
            imports = db.execute(
                text("""
                    SELECT id, module_name, package_name, qualified_style, is_hiding
                    FROM import
                    WHERE module_id = :module_id
                """),
                {"module_id": module_id}
            ).fetchall()
            
            module_data["content"]["imports"] = []
            
            for import_obj in imports:
                import_id, import_module, import_package, qualified_style, is_hiding = import_obj
                
                import_data = {
                    "id": f"import:{import_id}",
                    "module_name": import_module,
                    "package_name": import_package,
                    "qualified_style": qualified_style,
                    "is_hiding": is_hiding
                }
                
                module_data["content"]["imports"].append(import_data)
            
            extracted_data.append(module_data)
        
        return extracted_data
    
    finally:
        db.close()

def process_data_for_qdrant(extracted_data):
    """Process extracted data and store in Qdrant with parent-child relationships."""
    # Process data for each collection
    code_elements = []
    domain_knowledge = []
    code_review = []
    performance = []
    
    # Create a mapping of module names to their data for parent-child relationships
    module_map = {module_data["name"]: module_data for module_data in extracted_data}
    
    for module_data in tqdm(extracted_data, desc="Processing data for Qdrant"):
        # Process module-level data
        module_content = f"Module: {module_data['name']}\nPath: {module_data['path']}\n"
        
        # Add import information for context
        if module_data["content"].get("imports"):
            module_content += "\nImports:\n"
            for imp in module_data["content"]["imports"][:10]:  # Limit to first 10 imports
                module_content += f"- {imp.get('module_name', '')}\n"
        
        module_doc = {
            "id": module_data["id"],
            "payload": {
                "content": module_content,
                "type": "module",
                "name": module_data["name"],
                "module": module_data["name"],
                "parent": None,  # Modules are top-level
                "parent_type": None
            },
            "vectors": {
                "semantic_vector": generate_semantic_embedding(module_content),
                "code_vector": generate_code_embedding(module_content)
            }
        }
        
        code_elements.append(module_doc)
        
        # Process functions
        for function in module_data["content"]["functions"]:
            # Create function document with parent module context
            function_content = f"Function: {function['name']}\nSignature: {function.get('signature', '')}\nModule: {module_data['name']}\n\nImplementation:\n{function.get('raw_string', '')}\n"
            
            # Add parent module context
            function_content += f"\nParent Module:\n{module_data['name']}\n"
            
            # Add function call information for context
            if function.get("calls"):
                function_content += "\nCalls:\n"
                for call in function["calls"][:5]:  # Limit to first 5 calls
                    function_content += f"- {call.get('name', '')} in {call.get('module_name', '')}\n"
            
            # Generate summary using Azure OpenAI
            if function.get('raw_string'):
                summary = analyze_code_with_llm(function['raw_string'], "general")
                function_content += f"\nSummary:\n{summary}\n"
            
            function_doc = {
                "id": function["id"],
                "payload": {
                    "content": function_content,
                    "type": "function",
                    "name": function["name"],
                    "module": module_data["name"],
                    "line_start": function.get("line_start", 0),
                    "line_end": function.get("line_end", 0),
                    "complexity": function["metrics"]["complexity"],
                    "parent": module_data["id"],  # Reference to parent module
                    "parent_type": "module"
                },
                "vectors": {
                    "semantic_vector": generate_semantic_embedding(function_content),
                    "code_vector": generate_code_embedding(function.get('raw_string', ''))
                }
            }
            
            code_elements.append(function_doc)
            
            # If function is complex, add to performance collection
            if function["metrics"]["complexity"] > 5 or function["metrics"]["dependency_count"] > 10:
                # Analyze performance
                if function.get('raw_string'):
                    performance_analysis = analyze_code_with_llm(function['raw_string'], "performance")
                    
                    perf_doc = {
                        "id": f"performance:{function['id']}",
                        "payload": {
                            "content": f"Performance Analysis for Function: {function['name']}\nModule: {module_data['name']}\n\n{performance_analysis}",
                            "type": "performance_analysis",
                            "function_name": function["name"],
                            "module": module_data["name"],
                            "complexity": function["metrics"]["complexity"],
                            "dependency_count": function["metrics"]["dependency_count"],
                            "parent": function["id"],  # Reference to parent function
                            "parent_type": "function"
                        },
                        "vectors": {
                            "code_vector": generate_code_embedding(function.get('raw_string', ''))
                        }
                    }
                    
                    performance.append(perf_doc)
        
        # Process types
        for type_obj in module_data["content"]["types"]:
            # Create type document with parent module context
            type_content = f"Type: {type_obj['name']}\nModule: {module_data['name']}\n\nDefinition:\n{type_obj.get('raw_code', '')}\n"
            
            # Add parent module context
            type_content += f"\nParent Module:\n{module_data['name']}\n"
            
            # Add constructor information for context
            if type_obj.get("constructors"):
                type_content += "\nConstructors:\n"
                for constructor in type_obj["constructors"]:
                    type_content += f"- {constructor.get('name', '')}\n"
                    if constructor.get("fields"):
                        for field in constructor["fields"]:
                            type_content += f"  - {field.get('name', '')}: {field.get('type', '')}\n"
            
            type_doc = {
                "id": type_obj["id"],
                "payload": {
                    "content": type_content,
                    "type": "type_definition",
                    "name": type_obj["name"],
                    "module": module_data["name"],
                    "line_start": type_obj.get("line_start", 0),
                    "line_end": type_obj.get("line_end", 0),
                    "parent": module_data["id"],  # Reference to parent module
                    "parent_type": "module"
                },
                "vectors": {
                    "semantic_vector": generate_semantic_embedding(type_content),
                    "code_vector": generate_code_embedding(type_obj.get('raw_code', ''))
                }
            }
            
            code_elements.append(type_doc)
            
            # Process constructors as children of types
            for constructor in type_obj.get("constructors", []):
                constructor_content = f"Constructor: {constructor['name']}\nType: {type_obj['name']}\nModule: {module_data['name']}\n\n"
                
                # Add field information
                if constructor.get("fields"):
                    constructor_content += "Fields:\n"
                    for field in constructor["fields"]:
                        constructor_content += f"- {field.get('name', '')}: {field.get('type', '')}\n"
                
                constructor_doc = {
                    "id": constructor["id"],
                    "payload": {
                        "content": constructor_content,
                        "type": "constructor",
                        "name": constructor["name"],
                        "module": module_data["name"],
                        "parent": type_obj["id"],  # Reference to parent type
                        "parent_type": "type_definition"
                    },
                    "vectors": {
                        "semantic_vector": generate_semantic_embedding(constructor_content),
                        "code_vector": generate_code_embedding(constructor_content)
                    }
                }
                
                code_elements.append(constructor_doc)
        
        # Process classes
        for class_obj in module_data["content"]["classes"]:
            # Create class document with parent module context
            class_content = f"Class: {class_obj['name']}\nModule: {module_data['name']}\n\nDefinition:\n{class_obj.get('definition', '')}\n"
            
            # Add parent module context
            class_content += f"\nParent Module:\n{module_data['name']}\n"
            
            class_doc = {
                "id": class_obj["id"],
                "payload": {
                    "content": class_content,
                    "type": "class",
                    "name": class_obj["name"],
                    "module": module_data["name"],
                    "line_start": class_obj.get("line_start", 0),
                    "line_end": class_obj.get("line_end", 0),
                    "parent": module_data["id"],  # Reference to parent module
                    "parent_type": "module"
                },
                "vectors": {
                    "semantic_vector": generate_semantic_embedding(class_content),
                    "code_vector": generate_code_embedding(class_obj.get('definition', ''))
                }
            }
            
            code_elements.append(class_doc)
        
        # Extract domain knowledge
        # Combine some function code for domain analysis
        combined_code = "\n".join([f.get("raw_string", "") for f in module_data["content"]["functions"][:5] if f.get("raw_string")])
        if combined_code:
            domain_knowledge_text = analyze_code_with_llm(combined_code, "domain")
            
            domain_doc = {
                "id": f"domain:{module_data['id']}",
                "payload": {
                    "content": f"Domain Knowledge for Module: {module_data['name']}\n\n{domain_knowledge_text}",
                    "type": "domain_knowledge",
                    "name": f"Domain concepts for {module_data['name']}",
                    "module": module_data["name"],
                    "occurrence_count": 1,  # Placeholder
                    "parent": module_data["id"],  # Reference to parent module
                    "parent_type": "module"
                },
                "vectors": {
                    "semantic_vector": generate_semantic_embedding(domain_knowledge_text)
                }
            }
            
            domain_knowledge.append(domain_doc)
        
        # Generate code review insights
        combined_code = "\n".join([f.get("raw_string", "") for f in module_data["content"]["functions"][:3] if f.get("raw_string")])
        if combined_code:
            code_quality_analysis = analyze_code_with_llm(combined_code, "quality")
            
            review_doc = {
                "id": f"review:{module_data['id']}",
                "payload": {
                    "content": f"Code Quality Analysis for Module: {module_data['name']}\n\n{code_quality_analysis}",
                    "type": "code_quality",
                    "name": f"Quality analysis for {module_data['name']}",
                    "module": module_data["name"],
                    "issue_count": code_quality_analysis.count("issue") + code_quality_analysis.count("problem"),
                    "parent": module_data["id"],  # Reference to parent module
                    "parent_type": "module"
                },
                "vectors": {
                    "semantic_vector": generate_semantic_embedding(code_quality_analysis),
                    "code_vector": generate_code_embedding(combined_code)
                }
            }
            
            code_review.append(review_doc)
    
    # Upload points to Qdrant in batches
    batch_size = 100
    
    # Upload code elements
    print(f"Uploading {len(code_elements)} code elements to Qdrant...")
    for i in tqdm(range(0, len(code_elements), batch_size), desc="Uploading code elements"):
        batch = code_elements[i:i+batch_size]
        qdrant_client.upsert(
            collection_name="code_elements",
            points=[
                qdrant_models.PointStruct(
                    id=doc["id"],
                    payload=doc["payload"],
                    vectors=doc["vectors"]
                ) for doc in batch
            ]
        )
    
    # Upload domain knowledge
    print(f"Uploading {len(domain_knowledge)} domain knowledge documents to Qdrant...")
    for i in tqdm(range(0, len(domain_knowledge), batch_size), desc="Uploading domain knowledge"):
        batch = domain_knowledge[i:i+batch_size]
        qdrant_client.upsert(
            collection_name="domain_knowledge",
            points=[
                qdrant_models.PointStruct(
                    id=doc["id"],
                    payload=doc["payload"],
                    vectors=doc["vectors"]
                ) for doc in batch
            ]
        )
    
    # Upload code review
    print(f"Uploading {len(code_review)} code review documents to Qdrant...")
    for i in tqdm(range(0, len(code_review), batch_size), desc="Uploading code review"):
        batch = code_review[i:i+batch_size]
        qdrant_client.upsert(
            collection_name="code_review",
            points=[
                qdrant_models.PointStruct(
                    id=doc["id"],
                    payload=doc["payload"],
                    vectors=doc["vectors"]
                ) for doc in batch
            ]
        )
    
    # Upload performance
    print(f"Uploading {len(performance)} performance documents to Qdrant...")
    for i in tqdm(range(0, len(performance), batch_size), desc="Uploading performance"):
        batch = performance[i:i+batch_size]
        qdrant_client.upsert(
            collection_name="performance",
            points=[
                qdrant_models.PointStruct(
                    id=doc["id"],
                    payload=doc["payload"],
                    vectors=doc["vectors"]
                ) for doc in batch
            ]
        )
    
    print("Data processing and upload complete!")

if __name__ == "__main__":
    # Extract data from the database
    print("Extracting data from the database...")
    extracted_data = extract_data_from_db()
    
    # Process and upload data to Qdrant
    print("Processing and uploading data to Qdrant...")
    process_data_for_qdrant(extracted_data)
