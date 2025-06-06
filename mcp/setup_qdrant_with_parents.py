import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

# Load environment variables
load_dotenv()

def setup_qdrant_collections():
    """Set up Qdrant collections for code-as-data with parent-child relationships."""
    # Initialize Qdrant client
    client = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", 6333))
    )
    
    print("Setting up Qdrant collections...")
    
    # Create collection for code search
    print("Creating code_elements collection...")
    client.recreate_collection(
        collection_name="code_elements",
        vectors_config={
            "code_vector": qdrant_models.VectorParams(
                size=1536,  # Azure OpenAI embedding dimension
                distance=qdrant_models.Distance.COSINE
            ),
            "semantic_vector": qdrant_models.VectorParams(
                size=1536,  # Azure OpenAI embedding dimension
                distance=qdrant_models.Distance.COSINE
            )
        },
        # Define schema for filtering
        schema={
            "type": qdrant_models.PayloadSchemaType.KEYWORD,
            "name": qdrant_models.PayloadSchemaType.KEYWORD,
            "module": qdrant_models.PayloadSchemaType.KEYWORD,
            "line_start": qdrant_models.PayloadSchemaType.INTEGER,
            "line_end": qdrant_models.PayloadSchemaType.INTEGER,
            "complexity": qdrant_models.PayloadSchemaType.INTEGER,
            "parent": qdrant_models.PayloadSchemaType.KEYWORD,  # Parent ID for hierarchical relationships
            "parent_type": qdrant_models.PayloadSchemaType.KEYWORD  # Type of parent (module, class, etc.)
        }
    )
    
    # Create collection for domain knowledge
    print("Creating domain_knowledge collection...")
    client.recreate_collection(
        collection_name="domain_knowledge",
        vectors_config={
            "semantic_vector": qdrant_models.VectorParams(
                size=1536,
                distance=qdrant_models.Distance.COSINE
            )
        },
        schema={
            "type": qdrant_models.PayloadSchemaType.KEYWORD,
            "name": qdrant_models.PayloadSchemaType.KEYWORD,
            "module": qdrant_models.PayloadSchemaType.KEYWORD,
            "occurrence_count": qdrant_models.PayloadSchemaType.INTEGER,
            "parent": qdrant_models.PayloadSchemaType.KEYWORD,  # Parent ID for hierarchical relationships
            "parent_type": qdrant_models.PayloadSchemaType.KEYWORD  # Type of parent (module, class, etc.)
        }
    )
    
    # Create collection for code review
    print("Creating code_review collection...")
    client.recreate_collection(
        collection_name="code_review",
        vectors_config={
            "code_vector": qdrant_models.VectorParams(
                size=1536,
                distance=qdrant_models.Distance.COSINE
            ),
            "semantic_vector": qdrant_models.VectorParams(
                size=1536,
                distance=qdrant_models.Distance.COSINE
            )
        },
        schema={
            "type": qdrant_models.PayloadSchemaType.KEYWORD,
            "name": qdrant_models.PayloadSchemaType.KEYWORD,
            "module": qdrant_models.PayloadSchemaType.KEYWORD,
            "pattern_type": qdrant_models.PayloadSchemaType.KEYWORD,
            "compliance": qdrant_models.PayloadSchemaType.KEYWORD,
            "issue_count": qdrant_models.PayloadSchemaType.INTEGER,
            "parent": qdrant_models.PayloadSchemaType.KEYWORD,  # Parent ID for hierarchical relationships
            "parent_type": qdrant_models.PayloadSchemaType.KEYWORD  # Type of parent (module, class, etc.)
        }
    )
    
    # Create collection for performance optimization
    print("Creating performance collection...")
    client.recreate_collection(
        collection_name="performance",
        vectors_config={
            "code_vector": qdrant_models.VectorParams(
                size=1536,
                distance=qdrant_models.Distance.COSINE
            )
        },
        schema={
            "type": qdrant_models.PayloadSchemaType.KEYWORD,
            "module": qdrant_models.PayloadSchemaType.KEYWORD,
            "function_name": qdrant_models.PayloadSchemaType.KEYWORD,
            "complexity": qdrant_models.PayloadSchemaType.INTEGER,
            "dependency_count": qdrant_models.PayloadSchemaType.INTEGER,
            "parent": qdrant_models.PayloadSchemaType.KEYWORD,  # Parent ID for hierarchical relationships
            "parent_type": qdrant_models.PayloadSchemaType.KEYWORD  # Type of parent (function, module, etc.)
        }
    )
    
    print("Qdrant collections setup complete!")
    return client

if __name__ == "__main__":
    setup_qdrant_collections()
