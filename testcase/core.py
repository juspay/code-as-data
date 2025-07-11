import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from code_as_data.parsers.function_parser import FunctionParser
from code_as_data.parsers.class_parser import ClassParser
from code_as_data.parsers.import_parser import ImportParser
from code_as_data.parsers.type_parser import TypeParser
from code_as_data.parsers.instance_parser import InstanceParser
from code_as_data.networkx_adapter.networkx import NetworkxAdapter
from pyvis.network import Network
from testcase.llm import call_gemini
from testcase.types import MetaData, DetailedMetaData
from testcase.prompts import *
import networkx as nx
import time
import json 

def get_graph(fdep_path):
    function_parser = FunctionParser(fdep_path)
    class_parser = ClassParser(fdep_path)
    import_parser = ImportParser(fdep_path)
    type_parser = TypeParser(fdep_path)

    functions_by_module = function_parser.load()
    print("Starting class parsing...")
    classes_by_module = class_parser.load()
    print("Starting import parsing...")
    imports_by_module = import_parser.load()
    print("Starting type parsing...")
    types_by_module = type_parser.load()
    print("Processing instances...")
    instance_parser = InstanceParser(fdep_path, fdep_path, functions_by_module)
    instances_by_module = instance_parser.load_all_files()

    graph = NetworkxAdapter(instances_by_module,types_by_module,imports_by_module,functions_by_module,classes_by_module)
    graph.construct()

    return graph.get_graph_object()

def get_subgraph(G, handler):

    queue = [(handler, 0)]
    vis = set()
    g = nx.DiGraph()

    while queue:
        node,lvl = queue.pop(0) 
        if node in vis:
            continue 
        vis.add(node)
        g.add_node(node, **G.nodes[node])
        for child in G.successors(node):
            if G.nodes[child].get("node_type","") == "Function":
                queue.append((child,lvl+1))
                if child not in g.nodes():
                    g.add_node(child, **G.nodes[child])
                g.add_edge(node,child)

            if G.nodes[child].get("type","") == "where_function":
                for grandChild in G.successors(child):
                    if G.nodes[grandChild].get("node_type","") == "Function":
                        queue.append((grandChild,lvl+1))
                        if grandChild not in g.nodes():
                            g.add_node(grandChild, **G.nodes[grandChild])
                        g.add_edge(node,grandChild)

    return g

def get_visualize(g):
    net = Network(height="1000px", width="100%", bgcolor="#222222", font_color="white", directed=True)
    net.from_nx(g)
    net.show("graph.html", notebook=False)

def process_node(node, user_prompt, code, metainfo=None, response_schema=None, retries=3, cooldown=5):
    for attempt in range(retries):
        try:
            prompt = user_prompt.format(code=code,metadata=metainfo) if metainfo else user_prompt.format(code=code)
            result = call_gemini(user_prompt=prompt,response_format="application/json",response_schema=response_schema)
            return (node, json.loads(result))
        except Exception as e:
            print(f"❌ Error on {node} (attempt {attempt+1}): {e}")
            time.sleep(cooldown * (attempt + 1))
    return (node, None)

def get_child_metainfo(g, node):
    metainfo = ""
    for child in g.successors(node):
        child_info = get_metainfo(g, child)
        if child_info:
            metainfo += child_info + "\n"
    return metainfo.strip() if metainfo else None

def get_metainfo(g, node):
    data = g.nodes[node]
    
    behavior_summary = data.get("behavior_summary")
    if not behavior_summary:
        return ""

    pre = "\n".join(data.get("preconditions", []))
    post = "\n".join(data.get("postconditions", []))
    side = "\n".join(data.get("side_effects", []))

    state = data.get("state_dependencies") or {}
    db = state.get("db", "None")
    env = state.get("env", "None")
    redis = state.get("redis", "None")

    metainfo = (
            f"FunctionName: {node}\n"
            f"Short Summary: {behavior_summary}\n"
            f"Preconditions:\n{pre}\n"
            f"Postconditions:\n{post}\n"
            f"Side Effects:\n{side}\n"
            f"State Dependencies:\n"
            f"  DB: {db}\n"
            f"  Env: {env}\n"
            f"  Redis: {redis}"
        )
    return metainfo

def add_weights(g, node, relationships):
    
    for rel in relationships:
        child = rel.get("child",None)
        con = rel.get("condition",None)
        if child and g.has_edge(node, child):
            g[node][child]["condition"] = con
        else:
            g.add_edge(node, child, condition=con)

def process_graph(g, response_schema):
    queue = [] 
    for node in g.nodes():
        cnt = 0
        for child in g.successors(node):
            if g.nodes[child].get("node_type","") == "Function" or g.nodes[child].get("type","") == "where_function":
                cnt += 1
        g.nodes[node]["out"] = cnt 
        if cnt==0:
            queue.append(node)

    while queue:
        node = queue.pop(0)
        code = g.nodes[node].get("code_string",None)
        if code:
            metainfo = get_child_metainfo(g, node)
            prompt = parent_prompt if metainfo else child_prompt 

            _, result = process_node(node=node,code=code,metainfo=metainfo,user_prompt=prompt,response_schema=response_schema)
            if result:
                for k, v in result.items():
                    g.nodes[node][k] = v
                
                if result.get("child_call_relationship",None):
                    add_weights(g, node, result.get("child_call_relationship"))

                print(f"✅ Done: {node}")
            else:
                print(f"❌ Skipped: {node}")
            
        for par in g.predecessors(node):
            g.nodes[par]["out"] -= 1
            if g.nodes[par]["out"]==0:
                queue.append(par) 

    return g
