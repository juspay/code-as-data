
from code_as_data.parsers.function_parser import FunctionParser
from code_as_data.parsers.class_parser import ClassParser
from code_as_data.parsers.import_parser import ImportParser
from code_as_data.parsers.type_parser import TypeParser
from code_as_data.parsers.instance_parser import InstanceParser
from code_as_data.networkx_adapter.networkx import NetworkxAdapter
from prompts import user_prompt


fdep_path = "/Users/sakthi.n/Documents/Work/codegen/tmp"
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
G = graph.get_graph_object()

import json
from google import genai
from google.genai import types
from typing import Optional, List
from pydantic import BaseModel


class StateDependencies(BaseModel):
    db: Optional[List[str]]
    env: Optional[List[str]]                          
    redis: Optional[List[str]]                      

class MetaData(BaseModel):
    function_name: str
    behavior_summary: str
    preconditions: List[str]
    postconditions: List[str]
    state_dependencies: Optional[StateDependencies]
    side_effects: List[str]


def call_gemini(user_prompt: str, system_prompt=None, response_format="application/json"):
    client = genai.Client(
        api_key=""
    )

    model = "gemini-2.5-pro-preview-06-05"
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_prompt)],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type=response_format,
        response_schema=MetaData,
    )

    response = client.models.generate_content(
                model=model,
                config=generate_content_config,
                contents=contents,
            )
    return response.text


import concurrent.futures
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import time
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed

from networkx.readwrite import json_graph

# Save graph to JSON
def save_graph_json(G, path="graph.json"):
    data = json_graph.node_link_data(G, edges="edges")
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"💾 Graph saved to {path}")


def process_node(node, code, user_prompt, retries=3, cooldown=5):
    for attempt in range(retries):
        try:
            prompt = user_prompt.format(code=code)
            result = call_gemini(user_prompt=prompt)
            return (node, json.loads(result))
        except Exception as e:
            print(f"❌ Error on {node} (attempt {attempt+1}): {e}")
            time.sleep(cooldown * (attempt + 1))
    return (node, None)


def get_child_functions(node):
    funs = []
    for child in G.successors(node):
        if G.nodes[child].get("node_type","") == "Function" or G.nodes[child].get("type","") == "where_function":
            funs.append(child)
    return funs

def process_graph_parallel(G, user_prompt, checkpoint_file="graph.pickle", max_workers=4):
    tasks = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # for node in G.nodes():
        #     if G.nodes[node].get("node_type") == "Function" and '$' not in node:
        #         if G.nodes[node].get("function_name",None) or not G.nodes[node].get("code_string",None): 
        #             print("Already Processed.. skiping")
        #             continue

        #         code = G.nodes[node].get("code_string", "")
        #         tasks.append(executor.submit(process_node, node, code, user_prompt))

        handler = "App.Routes:generateCheckList"
        queue = [handler]

        visited = set() 

        while queue:
            node = queue.pop(0)
            if node in visited:
                continue 
            visited.add(node)
            print("curr Node: ", node)
            code = G.nodes[node].get("code_string",None)
            if code:
                tasks.append(executor.submit(process_node, node, code, user_prompt))
    
            for child in get_child_functions(node):
                queue.append(child)
            


        for future in as_completed(tasks):
            node, result = future.result()
            if result:
                for k, v in result.items():
                    G.nodes[node][k] = v
                print(f"✅ Done: {node}")
            else:
                print(f"❌ Skipped: {node}")
            
            # Save after each node
            with open(checkpoint_file, 'wb') as f:
                pickle.dump(G, f)
                print(f"💾 Saved after {node}\n")
                
            save_graph_json(G, path="graph.json")

    print("🎉 All nodes processed.")
    return G

process_graph_parallel(G=G,user_prompt=user_prompt)