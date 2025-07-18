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
from testcase.llm import call_gemini,count_tokens
from testcase.types import *
from testcase.prompts import *
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
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
            if G.nodes[child].get("node_type","") == "Function" and G.nodes[child].get("code_string",None):
                queue.append((child,lvl+1))
                if child not in g.nodes():
                    g.add_node(child, **G.nodes[child])
                g.add_edge(node,child)

            if G.nodes[child].get("type","") == "where_function" and G.nodes[child].get("code_string",None):
                for grandChild in G.successors(child):
                    if G.nodes[grandChild].get("node_type","") == "Function":
                        queue.append((grandChild,lvl+1))
                        if grandChild not in g.nodes():
                            g.add_node(grandChild, **G.nodes[grandChild])
                        g.add_edge(node,grandChild)
    return g

def get_visualize(g, path="graph.html"):
    net = Network(height="1000px", width="100%", bgcolor="#222222", font_color="white", directed=True)
    net.from_nx(g)
    net.show(path, notebook=False)

def get_visualize_with_weights(g, path="graph.html"):
    net = Network(height="1000px", width="100%", bgcolor="#222222", font_color="white", directed=True)

    for node in g.nodes():
        net.add_node(node, label=node)
    for source, target in g.edges():
        condition = g[source][target].get("condition", "")
        label = f"{condition}" if condition else ""
        net.add_edge(source, target, label=label)
    net.show(path, notebook=False)

def process_node(node, lvl, user_prompt, code, metainfo=None, response_schema=None, retries=3, cooldown=5):
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

def summarizer(currfun, nextfun, metainfos):
    con_metainfo = "" 
    for metainfo in metainfos:
        con_metainfo += metainfo 
        cnt = count_tokens(con_metainfo)
        if cnt.total_tokens > 900000:
            print(f"currently exceeding... {cnt.total_tokens}")
            prompt = summarize_prompt.format(current_function=currfun, next_function=nextfun, metainfo=con_metainfo)
            result = call_gemini(user_prompt=prompt,response_format="application/json",response_schema=MetaData)
            dct = json.loads(result)
            con_metainfo = f"FunctionName: {currfun.split(":")[-1]}\nshortsummary: {dct["behavior_summary"]}\npreconditions: \n{"\n".join(dct["preconditions"])}\nposconditions: \n{"\n".join(dct["postconditions"])}\nsideeffects: \n{"\n".join(dct["side_effects"])}\n"
            state_deps = dct.get("state_dependencies",None)
            if state_deps:
                con_metainfo += f"DB: {state_deps.get("db","None")}\nEnv: {state_deps.get("env","None")}\nRedis: {state_deps.get("redis","None")}\n\n"
            else:
                con_metainfo += "DB: None\nEnv: None\nRedis: None\n\n"
    
    prompt = summarize_prompt.format(current_function=currfun, next_function=nextfun, metainfo=con_metainfo)
    result = call_gemini(user_prompt=prompt,response_format="application/json",response_schema=MetaData)
    dct = json.loads(result)
    con_metainfo = f"FunctionName: {currfun.split(":")[-1]}\nshortsummary: {dct["behavior_summary"]}\npreconditions: \n{"\n".join(dct["preconditions"])}\nposconditions: \n{"\n".join(dct["postconditions"])}\nsideeffects: \n{"\n".join(dct["side_effects"])}\n"
    state_deps = dct.get("state_dependencies",None)
    if state_deps:
        con_metainfo += f"DB: {state_deps.get("db","None")}\nEnv: {state_deps.get("env","None")}\nRedis: {state_deps.get("redis","None")}\n\n"
    else:
        con_metainfo += "DB: None\nEnv: None\nRedis: None\n\n"
        
    return con_metainfo
        
def all_child_expectone(g, node, child):
    childs = [] 
    metainfo = ""

    queue = [node]
    vis = set()  
    while queue: 
        cnode = queue.pop(0) 
        if cnode in vis:
            continue 
        vis.add(cnode)

        if g.nodes[cnode].get("behavior_summary", None):
            metainfo += f"FunctionName: {cnode}\nshortsummary: {g.nodes[cnode]["behavior_summary"]}\npreconditions: \n{"\n".join(g.nodes[node]["preconditions"])}\nposconditions: \n{"\n".join(g.nodes[node]["postconditions"])}\nsideeffects: \n{"\n".join(g.nodes[node]["side_effects"])}\n"
            state_deps = g.nodes[cnode].get("state_dependencies",None)
            if state_deps:
                metainfo += f"DB: {state_deps.get("db","None")}\nEnv: {state_deps.get("env","None")}\nRedis: {state_deps.get("redis","None")}\n"
            else:
                metainfo += "DB: None\nEnv: None\nRedis: None\n"

        for c in g.successors(cnode):
            if g.nodes[c].get("node_type","") == "Function":
                if c != child:
                    queue.append(c)
                    childs.append(c)
            if g.nodes[c].get("type","") == "where_function":
                for grandchild in g.successors(c):
                    if grandchild != child:
                        queue.append(grandchild)
                        childs.append(grandchild)

    return childs, metainfo

def all_child_expectoneV2(g, node, child):
    childs = [] 
    metainfo = []

    queue = [(node, 0)]
    vis = set()  
    while queue: 
        cnode,lvl = queue.pop(0) 
        if cnode in vis:
            continue

        print("curr level: ",lvl)
            
        if lvl >= 2:
            break
        vis.add(cnode)

        cmetainfo = ""
        if g.nodes[cnode].get("behavior_summary", None):
            cmetainfo += f"FunctionName: {cnode}\nshortsummary: {g.nodes[cnode]["behavior_summary"]}\npreconditions: \n{"\n".join(g.nodes[node]["preconditions"])}\nposconditions: \n{"\n".join(g.nodes[node]["postconditions"])}\nsideeffects: \n{"\n".join(g.nodes[node]["side_effects"])}\n"
            state_deps = g.nodes[cnode].get("state_dependencies",None)
            if state_deps:
                cmetainfo += f"DB: {state_deps.get("db","None")}\nEnv: {state_deps.get("env","None")}\nRedis: {state_deps.get("redis","None")}\n"
            else:
                cmetainfo += "DB: None\nEnv: None\nRedis: None\n"

            metainfo.append(cmetainfo)

        for c in g.successors(cnode):
            if g.nodes[c].get("node_type","") == "Function":
                if c != child:
                    queue.append((c,lvl+1))
                    childs.append((c,lvl+1))
            if g.nodes[c].get("type","") == "where_function":
                for grandchild in g.successors(c):
                    if grandchild != child:
                        queue.append((grandchild,lvl+1))
                        childs.append((grandchild,lvl+1))

    return childs, metainfo

def all_childs(g, node):
    childs = [] 
    metainfo = ""

    queue = [node]
    vis = set()  
    while queue: 
        cnode = queue.pop(0) 
        if cnode in vis:
            continue 
        vis.add(cnode)

        if g.nodes[cnode].get("behavior_summary", None):
            metainfo += f"FunctionName: {cnode}\nshortsummary: {g.nodes[cnode]["behavior_summary"]}\npreconditions: \n{"\n".join(g.nodes[node]["preconditions"])}\nposconditions: \n{"\n".join(g.nodes[node]["postconditions"])}\nsideeffects: \n{"\n".join(g.nodes[node]["side_effects"])}\n"
            state_deps = g.nodes[cnode].get("state_dependencies",None)
            if state_deps:
                metainfo += f"DB: {state_deps.get("db","None")}\nEnv: {state_deps.get("env","None")}\nRedis: {state_deps.get("redis","None")}\n"
            else:
                metainfo += "DB: None\nEnv: None\nRedis: None\n"


        for c in g.successors(cnode):
            if g.nodes[c].get("node_type","") == "Function":
                    queue.append(c)
                    childs.append(c)
            if g.nodes[c].get("type","") == "where_function":
                for grandchild in g.successors(c):
                        queue.append(grandchild)
                        childs.append(grandchild)
    return childs,metainfo

def all_childsV2(g, node):
    childs = [] 
    metainfo = []

    queue = [(node, 0)]
    vis = set()  
    while queue: 
        cnode, lvl = queue.pop(0) 
        if cnode in vis:
            continue 
        vis.add(cnode)

        cmetainfo = ""
        if g.nodes[cnode].get("behavior_summary", None):
            cmetainfo += f"FunctionName: {cnode}\nshortsummary: {g.nodes[cnode]["behavior_summary"]}\npreconditions: \n{"\n".join(g.nodes[node]["preconditions"])}\nposconditions: \n{"\n".join(g.nodes[node]["postconditions"])}\nsideeffects: \n{"\n".join(g.nodes[node]["side_effects"])}\n"
            state_deps = g.nodes[cnode].get("state_dependencies",None)
            if state_deps:
                cmetainfo += f"DB: {state_deps.get("db","None")}\nEnv: {state_deps.get("env","None")}\nRedis: {state_deps.get("redis","None")}\n"
            else:
                cmetainfo += "DB: None\nEnv: None\nRedis: None\n"

            metainfo.append(cmetainfo)

        for c in g.successors(cnode):
            if g.nodes[c].get("node_type","") == "Function":
                    queue.append((c,lvl+1))
                    childs.append((c,lvl+1))
            if g.nodes[c].get("type","") == "where_function":
                for grandchild in g.successors(c):
                        queue.append((grandchild,lvl+1))
                        childs.append((grandchild,lvl+1))
    return childs,metainfo

def get_path_str(g, src, des):
    path = nx.shortest_path(g, src, des)
    path_str = ""
    for node in path:
        path_str += node + " -> "
    path_str = path_str.removesuffix(" -> ") 
    return (path, path_str)

def add_weights(g, node, relationships):
    
    for rel in relationships:
        child = rel.get("child",None)
        con = rel.get("condition",None)
        if child and g.has_edge(node, child):
            g[node][child]["condition"] = con

def get_topo_order(g):
    child_order = [] 
    queue = [] 
    print("cnt: ",len(g.nodes()))
    for node in g.nodes():
        cnt = 0
        for _ in g.successors(node):
            cnt += 1
        g.nodes[node]["out"] = cnt 
        if cnt==0:
            queue.append((node,0))
    while queue:
        node,lvl = queue.pop(0)
        child_order.append((node,lvl))            
        for par in g.predecessors(node):
            g.nodes[par]["out"] -= 1
            if g.nodes[par]["out"]==0:
                queue.append((par,lvl+1)) 
    return child_order

def process_graph(g, response_schema):
    queue = deque()
    for node in g.nodes():
        cnt = 0
        for _ in g.successors(node):
            cnt += 1
        g.nodes[node]["out"] = cnt 
        if cnt==0:
            queue.append((node,0))
    cnt = 1
    while queue:
        (node,lvl) = queue.popleft()
        print(cnt, node, lvl)
        cnt += 1
        code = g.nodes[node].get("code_string",None)
        if code:
            metainfo = get_child_metainfo(g, node)
            prompt = parent_promptv2 if metainfo else child_prompt 

            _, result = process_node(node=node,lvl=lvl,code=code,metainfo=metainfo,user_prompt=prompt,response_schema=response_schema)
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
                queue.append((par,lvl+1)) 

    return g

import pickle
import threading

def process_graph_parallel(g, response_schema, max_workers=10, checkpoint_every=50):
    # Step 1: Count number of callable children (out-degree) 
    queue = deque()
    hcnt = 0
    for node in g.nodes():
        cnt = 0
        for _ in g.successors(node):
            cnt += 1
        g.nodes[node]["out"] = cnt
        if cnt == 0:
            queue.append((node, 0))
        hcnt += 1

    print(hcnt)

    # Step 2: Run batch processing in parallel
    cnt = 0
    lock = threading.Lock()  # For thread-safe operations
    
    while queue:
        # Process all nodes at current level in parallel
        current_batch = list(queue)
        queue.clear()
        
        if not current_batch:
            break
            
        next_queue = deque()
        futures = {}
        processed_in_batch = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs for current batch
            for (node, lvl) in current_batch:
                code = g.nodes[node].get("code_string")
                if not code:
                    continue

                # Skip if already processed
                if g.nodes[node].get("behaviour_summary") is not None:
                    continue

                metainfo = get_child_metainfo(g, node)
                prompt = parent_promptv2 if metainfo else child_prompt

                futures[executor.submit(
                    process_node,
                    node=node,
                    lvl=lvl,  # Pass level to process_node like in single-threaded
                    code=code,
                    metainfo=metainfo,
                    user_prompt=prompt,
                    response_schema=response_schema
                )] = (node, lvl)

            # Process completed futures
            for future in as_completed(futures):
                node, lvl = futures[future]
                try:
                    _, result = future.result()
                except Exception as e:
                    print(f"❌ Error in node {node}: {e}")
                    with lock:
                        cnt += 1
                    continue

                # Thread-safe updates to graph and counter
                with lock:
                    if result:
                        for k, v in result.items():
                            g.nodes[node][k] = v
                        if result.get("child_call_relationship"):
                            add_weights(g, node, result["child_call_relationship"])

                        # print(f"{cnt} ✅ Done: {node} {lvl}")
                    else:
                        # print(f"{cnt} ❌ Skipped: {node} {lvl}")
                        print("",end="")
                
                    processed_in_batch += 1

                    # ✅ Save every `checkpoint_every` nodes
                    if processed_in_batch % checkpoint_every == 0:
                        try:
                            with open('final.gpickle', 'wb') as f:
                                pickle.dump(g, f)
                            print(f"💾 Intermediate save after {processed_in_batch} nodes")
                        except Exception as e:
                            print(f"⚠️ Failed to save checkpoint: {e}")

            with lock:
                for (node, lvl) in current_batch:
                    cnt += 1
                    print(f"{cnt} ✅ Done: {node} {lvl}")
                    for par in g.predecessors(node):
                        g.nodes[par]["out"] -= 1
                        if g.nodes[par]["out"]==0:
                            next_queue.append((par,lvl+1))  

        # Final save for the batch
        try:
            with open('final.gpickle', 'wb') as f:
                pickle.dump(g, f)
            print(f"💾 Final save after batch of {processed_in_batch} nodes")
        except Exception as e:
            print(f"⚠️ Failed to save final batch: {e}")

        queue = next_queue

    return g