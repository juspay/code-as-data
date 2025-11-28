#!/usr/bin/env python3
"""
NetworkX graph exporter for code-as-data.
Exports comprehensive graphs from Haskell and Rust codebases to multiple formats.
"""
import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Set
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict
import html
import chardet
from bs4 import BeautifulSoup

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from code_as_data.parsers.function_parser import FunctionParser
from code_as_data.parsers.impl_block_parser import ImplBlockParser
from code_as_data.parsers.type_parser import TypeParser
from code_as_data.parsers.trait_parser import TraitParser
from code_as_data.parsers.constant_parser import ConstantParser
from code_as_data.parsers.trait_method_signature_parser import TraitMethodSignatureParser
from code_as_data.parsers.import_parser import ImportParser
from code_as_data.parsers.module_parser import ModuleParser
from code_as_data.parsers.instance_parser import InstanceParser
from code_as_data.parsers.class_parser import ClassParser
from code_as_data.networkx_adapter.networkx import NetworkxAdapter

def detect_languages(fdep_path: str) -> Dict[str, int]:
    """
    Detect which languages are present in the fdep_path.
    
    Args:
        fdep_path: Path to the dump files
        
    Returns:
        Dictionary with language counts
    """
    languages = {"haskell": 0, "rust": 0}
    
    if not os.path.exists(fdep_path):
        return languages
    
    for root, dirs, files in os.walk(fdep_path):
        for file in files:
            if file.endswith('.hs.json'):
                languages["haskell"] += 1
            elif file.endswith('.json') and not file.endswith('.hs.json'):
                languages["rust"] += 1
    
    return languages

def create_codebase_graph(fdep_path: str) -> nx.DiGraph:
    """
    Create a comprehensive NetworkX graph using all existing parsers.
    Automatically detects and processes both Haskell and Rust files.
    
    Args:
        fdep_path: Path to the fdep_output directory
        
    Returns:
        NetworkX DiGraph with all relationships
    """
    print("🔍 Creating Codebase Graph (Haskell + Rust)")
    print("=" * 60)
    
    # Detect languages
    languages = detect_languages(fdep_path)
    print(f"📊 Language Detection:")
    print(f"  Haskell files: {languages['haskell']}")
    print(f"  Rust files: {languages['rust']}")
    
    if languages['haskell'] == 0 and languages['rust'] == 0:
        print("⚠️  No supported language files found!")
        return nx.DiGraph()
    
    # Initialize all parsers (they handle both languages automatically)
    print("📚 Initializing parsers...")
    function_parser = FunctionParser(fdep_path)
    impl_block_parser = ImplBlockParser(fdep_path)
    type_parser = TypeParser(fdep_path)
    trait_parser = TraitParser(fdep_path)
    constant_parser = ConstantParser(fdep_path)
    trait_sig_parser = TraitMethodSignatureParser(fdep_path)
    import_parser = ImportParser(fdep_path)
    instance_parser = InstanceParser(fdep_path, fdep_path)  # path, base_dir_path
    class_parser = ClassParser(fdep_path)
    
    # Load all data using existing parsers (language-agnostic)
    print("📄 Loading functions (Haskell + Rust)...")
    functions_by_module = function_parser.load()
    
    print("📄 Loading impl blocks (Rust)...")
    impl_blocks_by_module = impl_block_parser.load()
    
    print("📄 Loading types (Haskell + Rust)...")
    types_by_module = type_parser.load()
    
    print("📄 Loading traits (Rust)...")
    traits_by_module = trait_parser.load()
    
    print("📄 Loading constants (Rust)...")
    constants_by_module = constant_parser.load()
    
    print("📄 Loading trait method signatures (Rust)...")
    trait_sigs_by_module = trait_sig_parser.load()
    
    print("📄 Loading imports (Haskell + Rust)...")
    imports_by_module = import_parser.load()
    
    print("📄 Loading instances (Haskell)...")
    try:
        instances_by_module = instance_parser.load_all_files()
    except Exception as e:
        print(f"⚠️  Instance parser failed: {e}, using empty instances")
        instances_by_module = {}
    
    print("📄 Loading classes (Haskell)...")
    try:
        classes_by_module = class_parser.load()
    except Exception as e:
        print(f"⚠️  Class parser failed: {e}, using empty classes")
        classes_by_module = {}
    
    # Create NetworkX adapter with all data
    print("🏗️  Building codebase graph...")
    adapter = NetworkxAdapter(
        instances_by_module=instances_by_module,      # Haskell
        types_by_module=types_by_module,              # Both
        imports_by_module=imports_by_module,          # Both
        functions_by_module=functions_by_module,      # Both
        classes_by_module=classes_by_module,          # Haskell
        impl_blocks_by_module={},                     # Disable impl blocks to avoid errors
        constants_by_module=constants_by_module,      # Rust
        trait_sigs_by_module=trait_sigs_by_module,    # Rust
        traits_by_module=traits_by_module,            # Rust
        modules_by_name={},  # Disable for now to avoid errors
    )
    
    # Build the complete graph
    adapter.construct()
    G = adapter.get_graph_object()
    
    return G

def clean_node_ids_and_create_mapping(G: nx.DiGraph) -> tuple[nx.DiGraph, dict]:
    """
    Clean HTML entities from node IDs and create a new graph with clean IDs.
    
    Args:
        G: Original NetworkX graph
        
    Returns:
        Tuple of (cleaned graph, mapping from old to new IDs)
    """
    print("🧹 Cleaning node IDs and creating clean graph...")
    
    # Create mapping from old to new node IDs
    id_mapping = {}
    for node_id in G.nodes():
        clean_id = clean_html_entities(str(node_id))
        id_mapping[node_id] = clean_id
    
    # Create new graph with clean node IDs
    clean_G = nx.DiGraph()
    
    # Add nodes with clean IDs and cleaned data
    for old_id, data in G.nodes(data=True):
        clean_id = id_mapping[old_id]
        clean_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                clean_data[key] = clean_html_entities(value)
            else:
                clean_data[key] = value
        clean_G.add_node(clean_id, **clean_data)
    
    # Add edges with clean source/target IDs
    for source, target, data in G.edges(data=True):
        clean_source = id_mapping[source]
        clean_target = id_mapping[target]
        clean_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                clean_data[key] = clean_html_entities(value)
            else:
                clean_data[key] = value
        clean_G.add_edge(clean_source, clean_target, **clean_data)
    
    return clean_G, id_mapping

def add_graphml_attributes(G: nx.DiGraph) -> nx.DiGraph:
    """
    Add proper GraphML attributes to nodes and edges for export.
    
    Args:
        G: NetworkX graph
        
    Returns:
        Graph with GraphML attributes
    """
    print("🎨 Adding GraphML attributes...")
    
    # First clean all node IDs and data
    clean_G, id_mapping = clean_node_ids_and_create_mapping(G)
    
    # Add proper attributes for GraphML export
    for node_id, data in clean_G.nodes(data=True):
        # Clean up None values and ensure all attributes are strings
        cleaned_data = {}
        for key, value in data.items():
            if value is None:
                cleaned_data[key] = ""
            elif isinstance(value, (list, dict)):
                cleaned_data[key] = json.dumps(value)
            else:
                cleaned_data[key] = str(value)
        
        # Determine category based on node_type
        node_type = cleaned_data.get('node_type', 'unknown')
        if node_type == 'Function':
            category = "function"
        elif node_type == 'Type':
            category = "type"
        elif node_type == 'Trait':
            category = "trait"
        elif node_type == 'ImplBlock':
            category = "impl"
        elif node_type == 'Constant':
            category = "constant"
        elif node_type == 'Import':
            category = "import"
        elif node_type == 'Module':
            category = "module"
        elif node_type == 'TraitMethodSignature':
            category = "trait_method"
        elif node_type == 'Class':
            category = "class"
        elif node_type == 'Instance':
            category = "instance"
        elif 'where_function' in node_type:
            category = "where_function"
        elif 'constructor' in node_type:
            category = "constructor"
        elif 'field' in node_type:
            category = "field"
        else:
            category = node_type.lower()
        
        # Create location info
        location = {
            "start": cleaned_data.get('line_number_start', '1'),
            "end": cleaned_data.get('line_number_end', '1'),
            "module": cleaned_data.get('src_loc', node_id)
        }
        
        # Set GraphML attributes (all as strings, already cleaned)
        clean_G.nodes[node_id].clear()  # Clear existing data
        clean_G.nodes[node_id]['category'] = category
        clean_G.nodes[node_id]['location'] = json.dumps(location)
        clean_G.nodes[node_id]['returns'] = "None"
        clean_G.nodes[node_id]['parameters'] = "[]"
        clean_G.nodes[node_id]['label'] = cleaned_data.get('label', node_id.split('::')[-1])
    
    # Add relation attributes to edges
    for source, target, data in clean_G.edges(data=True):
        edge_type = data.get('type', 'unknown')
        if edge_type == 'calls':
            relation = "calls"
        elif edge_type == 'implements':
            relation = "implements_for"
        elif edge_type == 'defines_method':
            relation = "has"
        elif edge_type == 'where':
            relation = "contains"
        elif edge_type == 'uses_instance':
            relation = "uses"
        elif edge_type == 'HAS_FIELD':
            relation = "has_field"
        elif edge_type == 'USES_TYPE':
            relation = "uses_type"
        elif edge_type == 'DECLARES':
            relation = "declares"
        elif edge_type == 'instance_defines':
            relation = "defines"
        elif edge_type == 'has_import':
            relation = "imports"
        else:
            relation = edge_type
        
        # Clean edge data
        clean_G.edges[source, target].clear()
        clean_G.edges[source, target]['relation'] = relation
    
    return clean_G

def print_graph_statistics(G: nx.DiGraph, 
                         functions_by_module: Dict,
                         impl_blocks_by_module: Dict,
                         types_by_module: Dict,
                         traits_by_module: Dict,
                         constants_by_module: Dict,
                         instances_by_module: Dict,
                         classes_by_module: Dict,
                         languages: Dict):
    """Print detailed statistics about the graph."""
    print("\n📈 Codebase Graph Statistics:")
    print("=" * 60)
    print(f"Total Nodes: {G.number_of_nodes()}")
    print(f"Total Edges: {G.number_of_edges()}")
    
    # Language breakdown
    print(f"\nLanguage Breakdown:")
    print(f"  Haskell files: {languages['haskell']}")
    print(f"  Rust files: {languages['rust']}")
    
    # Count by node type
    node_types = defaultdict(int)
    for _, data in G.nodes(data=True):
        category = data.get('category', 'Unknown')
        node_types[category] += 1
    
    print("\nNode Categories:")
    for node_type, count in sorted(node_types.items()):
        print(f"  {node_type}: {count}")
    
    # Count by edge type
    edge_types = defaultdict(int)
    for _, _, data in G.edges(data=True):
        relation = data.get('relation', 'unknown')
        edge_types[relation] += 1
    
    print("\nEdge Relations:")
    for edge_type, count in sorted(edge_types.items()):
        print(f"  {edge_type}: {count}")
    
    # Detailed component statistics
    print(f"\nDetailed Component Statistics:")
    print(f"Modules Processed: {len(functions_by_module)}")
    
    total_functions = sum(len(funcs) for funcs in functions_by_module.values())
    total_impl_blocks = sum(len(impls) for impls in impl_blocks_by_module.values())
    total_types = sum(len(types) for types in types_by_module.values())
    total_traits = sum(len(traits) for traits in traits_by_module.values())
    total_constants = sum(len(consts) for consts in constants_by_module.values())
    total_instances = sum(len(insts) for insts in instances_by_module.values())
    total_classes = sum(len(classes) for classes in classes_by_module.values())
    
    print(f"Total Functions: {total_functions}")
    print(f"Total Impl Blocks: {total_impl_blocks} (Rust)")
    print(f"Total Types: {total_types}")
    print(f"Total Traits: {total_traits} (Rust)")
    print(f"Total Constants: {total_constants} (Rust)")
    print(f"Total Instances: {total_instances} (Haskell)")
    print(f"Total Classes: {total_classes} (Haskell)")
    
    # Relationship analysis
    calls_edges = sum(1 for _, _, data in G.edges(data=True) if data.get('relation') == 'calls')
    contains_edges = sum(1 for _, _, data in G.edges(data=True) if data.get('relation') == 'contains')
    impl_edges = sum(1 for _, _, data in G.edges(data=True) if data.get('relation') == 'implements_for')
    has_edges = sum(1 for _, _, data in G.edges(data=True) if data.get('relation') == 'has')
    
    print(f"\nRelationship Analysis:")
    print(f"Function Calls: {calls_edges}")
    print(f"Contains (where functions): {contains_edges}")
    print(f"Implements: {impl_edges}")
    print(f"Has (methods/fields): {has_edges}")

def parse_html_to_text(file_path: str) -> str:
    """Parse HTML-encoded text and return clean text."""
    with open(file_path, 'rb') as f:
        raw = f.read()
    guess = chardet.detect(raw)
    encoding = guess.get('encoding') or 'utf-8'
    text = raw.decode(encoding, errors='replace')
    # Strip HTML safely if present
    soup = BeautifulSoup(text, 'html.parser')
    plain = html.unescape(soup.get_text(separator='\n'))
    return plain

def clean_html_entities(text: str) -> str:
    """Clean HTML entities from a text string."""
    if not text:
        return text
    # Direct HTML entity unescaping without BeautifulSoup parsing
    # This preserves the original text structure while just unescaping entities
    return html.unescape(text)

def clean_graphml_file(file_path: str):
    """Clean HTML entities from GraphML file using direct text replacement."""
    print(f"🧹 Cleaning HTML entities from '{file_path}'...")
    
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Direct HTML entity unescaping using html.unescape
    cleaned_content = html.unescape(content)
    
    # Write back the cleaned content
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_content)
    
    print(f"✅ Cleaned HTML entities in '{file_path}'")

def export_graph(G: nx.DiGraph, output_dir: str, base_name: str):
    """Export the graph to multiple formats."""
    import pickle
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"💾 Exporting graph to '{output_dir}'...")
    
    # Export to GraphML format
    graphml_file = os.path.join(output_dir, f"{base_name}.graphml")
    nx.write_graphml(G, graphml_file)
    
    # Clean HTML entities from GraphML
    clean_graphml_file(graphml_file)
    print(f"✅ Graph exported to '{graphml_file}' (GraphML format)")
    
    # Export to gpickle format
    gpickle_file = os.path.join(output_dir, f"{base_name}.gpickle")
    with open(gpickle_file, 'wb') as f:
        pickle.dump(G, f)
    print(f"✅ Graph exported to '{gpickle_file}' (gpickle format)")
    
    # Export to GEXF format
    gexf_file = os.path.join(output_dir, f"{base_name}.gexf")
    nx.write_gexf(G, gexf_file)
    print(f"✅ Graph exported to '{gexf_file}' (GEXF format)")
    
    return graphml_file, gpickle_file, gexf_file

def visualize_graph(G: nx.DiGraph, languages: Dict, output_file: str):
    """Create a visualization of the graph."""
    print(f"📊 Creating visualization with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges...")
    
    # Create figure
    plt.figure(figsize=(24, 18))
    
    # Calculate layout
    if G.number_of_nodes() > 300:
        # Use a faster layout for very large graphs
        pos = nx.spring_layout(G, k=0.2, iterations=10)
    elif G.number_of_nodes() > 150:
        pos = nx.spring_layout(G, k=0.3, iterations=15)
    elif G.number_of_nodes() > 50:
        pos = nx.spring_layout(G, k=0.5, iterations=25)
    else:
        pos = nx.spring_layout(G, k=1, iterations=50)
    
    # Color nodes by category
    node_colors = []
    node_sizes = []
    for node_id, node_data in G.nodes(data=True):
        category = node_data.get('category', 'unknown')
        if category == 'module':
            node_colors.append('red')
            node_sizes.append(3000)
        elif category == 'function':
            node_colors.append('lightblue')
            node_sizes.append(1000)
        elif category == 'type':
            node_colors.append('lightgreen')
            node_sizes.append(1200)
        elif category == 'trait':
            node_colors.append('pink')
            node_sizes.append(1200)
        elif category == 'impl':
            node_colors.append('orange')
            node_sizes.append(800)
        elif category == 'constant':
            node_colors.append('yellow')
            node_sizes.append(600)
        elif category == 'import':
            node_colors.append('lightcyan')
            node_sizes.append(400)
        elif category == 'trait_method':
            node_colors.append('lavender')
            node_sizes.append(600)
        elif category == 'class':
            node_colors.append('lightcoral')
            node_sizes.append(1200)
        elif category == 'instance':
            node_colors.append('lightyellow')
            node_sizes.append(800)
        elif category == 'where_function':
            node_colors.append('lightpink')
            node_sizes.append(500)
        elif category == 'constructor':
            node_colors.append('lightsteelblue')
            node_sizes.append(600)
        elif category == 'field':
            node_colors.append('lightgoldenrodyellow')
            node_sizes.append(300)
        else:
            node_colors.append('lightgray')
            node_sizes.append(400)
    
    # Draw the graph
    nx.draw(G, pos,
           node_color=node_colors,
           node_size=node_sizes,
           with_labels=True,
           labels={node: data.get('label', node.split('::')[-1][:12]) for node, data in G.nodes(data=True)},
           font_size=3,
           font_weight='bold',
           arrows=True,
           edge_color='gray',
           alpha=0.7,
           arrowsize=6)
    
    # Title with language info
    title = f"Codebase Graph (Haskell: {languages['haskell']}, Rust: {languages['rust']})"
    plt.title(title, fontsize=20, fontweight='bold')
    
    # Add comprehensive legend
    legend_elements = [
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=15, label='Module'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='lightblue', markersize=12, label='Function'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='lightgreen', markersize=12, label='Type'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='pink', markersize=12, label='Trait (Rust)'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='orange', markersize=10, label='Impl Block (Rust)'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='lightcoral', markersize=12, label='Class (Haskell)'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='lightyellow', markersize=10, label='Instance (Haskell)'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='yellow', markersize=8, label='Constant'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='lightcyan', markersize=6, label='Import'),
        plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='lightpink', markersize=6, label='Where Function')
    ]
    plt.legend(handles=legend_elements, loc='upper right', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✅ Graph visualization saved as '{output_file}'")

def main():
    """Main function to create and export codebase graph."""
    parser = argparse.ArgumentParser(description='Export NetworkX graph from code-as-data dumps')
    parser.add_argument('--input', '-i', default='fdep_output', 
                       help='Input directory containing dump files (default: fdep_output)')
    parser.add_argument('--output', '-o', default='networkx_graph_exports', 
                       help='Output directory for graph files (default: networkx_graph_exports)')
    parser.add_argument('--name', '-n', default='codebase_graph', 
                       help='Base name for output files (default: codebase_graph)')
    parser.add_argument('--no-viz', action='store_true', 
                       help='Skip visualization generation')
    
    args = parser.parse_args()
    
    fdep_path = args.input
    output_dir = args.output
    base_name = args.name
    
    if not os.path.exists(fdep_path):
        print(f"❌ Input directory '{fdep_path}' not found!")
        return 1
    
    try:
        # Detect languages first
        languages = detect_languages(fdep_path)
        
        # Create graph using existing parsers
        G = create_codebase_graph(fdep_path)
        
        if G.number_of_nodes() == 0:
            print("⚠️  No graph nodes created. Check your input files.")
            return 1
        
        # Add GraphML attributes
        G = add_graphml_attributes(G)
        
        # Get the data for statistics (reload to get fresh data)
        function_parser = FunctionParser(fdep_path)
        impl_block_parser = ImplBlockParser(fdep_path)
        type_parser = TypeParser(fdep_path)
        trait_parser = TraitParser(fdep_path)
        constant_parser = ConstantParser(fdep_path)
        instance_parser = InstanceParser(fdep_path, fdep_path)
        class_parser = ClassParser(fdep_path)
        
        functions_by_module = function_parser.load()
        impl_blocks_by_module = impl_block_parser.load()
        types_by_module = type_parser.load()
        traits_by_module = trait_parser.load()
        constants_by_module = constant_parser.load()
        try:
            instances_by_module = instance_parser.load_all_files()
        except Exception as e:
            print(f"⚠️  Instance parser failed in stats: {e}")
            instances_by_module = {}
        classes_by_module = class_parser.load()
        
        # Print statistics
        print_graph_statistics(G, functions_by_module, impl_blocks_by_module, 
                             types_by_module, traits_by_module, constants_by_module,
                             instances_by_module, classes_by_module, languages)
        
        # Create visualization if requested
        if not args.no_viz:
            viz_file = os.path.join(output_dir, f"{base_name}.png")
            os.makedirs(output_dir, exist_ok=True)
            visualize_graph(G, languages, viz_file)
        
        # Export to multiple formats
        graphml_file, gpickle_file, gexf_file = export_graph(G, output_dir, base_name)
        
        print(f"\n🎉 Graph export complete!")
        print(f"Output directory: {output_dir}")
        print(f"Files created:")
        if not args.no_viz:
            print(f"  - {base_name}.png (visualization)")
        print(f"  - {base_name}.graphml (GraphML format)")
        print(f"  - {base_name}.gpickle (gpickle format)")
        print(f"  - {base_name}.gexf (GEXF format)")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error creating graph: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
