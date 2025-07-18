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
            if c != child:
                queue.append(c)
                childs.append(c)
        
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
            queue.append(c)
            childs.append(c)
        

    return childs,metainfo