
from code_as_data.models.type_model import *
from code_as_data.models.class_model import *
from code_as_data.models.function_model import *
from code_as_data.models.import_model import *
from code_as_data.models.instance_model import *
from code_as_data.parsers.class_parser import *
from code_as_data.parsers.function_parser import *
from code_as_data.parsers.import_parser import *
from code_as_data.parsers.instance_parser import *
from code_as_data.parsers.type_parser import *
import networkx as nx
import pickle

def generate_light_networkx(fdep_path,pickle_file_path_with_name):
    # class_parser = ClassParser(json_path=fdep_path)
    function_parser = FunctionParser(fdep_path=fdep_path, light_version=True)
    # import_parser = ImportParser(raw_code_path=fdep_path)
    type_parser = TypeParser(raw_code_path=fdep_path)

    # Load data
    # print("Loading data from parsers...")
    # all_classes = class_parser.load()
    # print(f"Loaded {sum(len(v) for v in all_classes.values())} classes.")

    all_functions = function_parser.load()
    print(f"Loaded {sum(len(v) for v in all_functions.values())} top-level functions.")

    # all_imports = import_parser.load()
    # print(f"Loaded {sum(len(v) for v in all_imports.values())} import records.")

    instance_parser = InstanceParser(path=fdep_path, base_dir_path=fdep_path, module_vs_functions=all_functions)
    all_instances = instance_parser.load_all_files()
    print(f"Loaded {sum(len(v) for v in all_instances.values())} instances.")

    all_types = type_parser.load()
    print(f"Loaded {sum(len(v) for v in all_types.values())} types.")
    G = nx.DiGraph()

    def generate_and_link_instance_functions():
        def remove_qualified_prefixes(input_string):
            words = input_string.split()
            processed_words = []
            for word in words:
                if "." in word:
                    processed_words.append(word.split(".")[-1])
                else:
                    processed_words.append(word)
            return " ".join(processed_words)
        instance_signature_to_instance_mapping = dict()
        for (im,il) in all_instances.items():
            instance_signature_to_instance_mapping[im] = dict()
            for i in il:
                instance_signature_to_instance_mapping[im][remove_qualified_prefixes(i.instance_signature)] = i
        return instance_signature_to_instance_mapping

    instance_signature_mapping = generate_and_link_instance_functions()

    for m, f in all_functions.items():
        for functionBody in f:
            function_name_without_src = functionBody.function_name.split("**")[0]
            function_name_with_module = f"{m}--{function_name_without_src}"
            G.add_node(function_name_with_module,signature=functionBody.function_signature,code=functionBody.raw_string,instances=list(set(functionBody.instances_used)))
            instances_used = functionBody.instances_used
            def traverseWhereFunctions(functionBody:Function):
                try:
                    functions_called = functionBody.functions_called
                    where_functions = functionBody.where_functions

                    def traverseFunctionsCalled(functions_called:list[FunctionCalled]):
                        for i in functions_called:
                            name_without_src = i.name.split("**")[0]
                            called_function_full_name = (
                                f'{i.module_name}--{name_without_src}'
                            )
                            G.add_node(called_function_full_name)
                            G.add_edge(function_name_with_module, called_function_full_name)
                    traverseFunctionsCalled(functions_called)
                    for j, jBody in where_functions.items():
                        traverseWhereFunctions(jBody)
                except Exception as e:
                    print(functionBody)
            for instance_signature in instances_used:
                instances_related = []
                for im, icl in instance_signature_mapping.items():
                    if icl.get(instance_signature) != None:
                        instances_related.append((im, icl.get(instance_signature)))

                for (instance_module, instance_functions) in instances_related:
                    for instance_function in  instance_functions.functions:
                        (function_module_name,function_id) = (instance_function.module_name,instance_function.function_name)
                        called_function_full_name = (
                            instance_module
                            + "--"
                            + function_id.split("**")[0]
                        )
                        G.add_node(called_function_full_name)
                        # G.add_edge(function_name_with_module, called_function_full_name)
                        for i in all_functions.get(function_module_name,[]):
                            if i.function_name == function_id:
                                ifunc_body = i
                                if ifunc_body != None:
                                    traverseWhereFunctions(ifunc_body)
            traverseWhereFunctions(functionBody)

    def extract_dependent_type_ids(complex_type: ComplexType):
        """Recursively extract type dependencies (type IDs) from a ComplexType."""
        deps = set()

        if complex_type.variant == TypeVariant.ATOMIC and complex_type.atomic_component:
            # Full qualified type id: module:type
            dep = f"{complex_type.atomic_component.module_name}:{complex_type.atomic_component.type_name}"
            if dep:
                deps.add(dep)

        elif complex_type.variant in {
            TypeVariant.LIST,
            TypeVariant.BANG,
            TypeVariant.DOC,
            TypeVariant.KIND_SIG,
        }:
            subtypes = [
                complex_type.list_type,
                complex_type.bang_type,
                complex_type.doc_type,
                complex_type.kind_type,
                complex_type.kind_sig,
            ]
            for t in subtypes:
                if t:
                    deps |= extract_dependent_type_ids(t)

        elif complex_type.variant in {TypeVariant.APP}:
            if complex_type.app_func:
                deps |= extract_dependent_type_ids(complex_type.app_func)
            if complex_type.app_args:
                for arg in complex_type.app_args:
                    deps |= extract_dependent_type_ids(arg)

        elif complex_type.variant in {TypeVariant.FUNC}:
            if complex_type.func_arg:
                deps |= extract_dependent_type_ids(complex_type.func_arg)
            if complex_type.func_result:
                deps |= extract_dependent_type_ids(complex_type.func_result)

        elif complex_type.variant in {TypeVariant.FORALL}:
            if complex_type.forall_body:
                deps |= extract_dependent_type_ids(complex_type.forall_body)

        elif complex_type.variant in {TypeVariant.QUAL}:
            if complex_type.qual_context:
                for ctx in complex_type.qual_context:
                    deps |= extract_dependent_type_ids(ctx)
            if complex_type.qual_body:
                deps |= extract_dependent_type_ids(complex_type.qual_body)

        elif (
            complex_type.variant in {TypeVariant.RECORD} and complex_type.record_fields
        ):
            for _, field_type in complex_type.record_fields:
                deps |= extract_dependent_type_ids(field_type)

        elif complex_type.variant in {TypeVariant.TUPLE, TypeVariant.PROMOTED_TUPLE}:
            if complex_type.tuple_types:
                for t in complex_type.tuple_types:
                    deps |= extract_dependent_type_ids(t)

        elif complex_type.variant in {TypeVariant.PROMOTED_LIST}:
            if complex_type.promoted_list_types:
                for t in complex_type.promoted_list_types:
                    deps |= extract_dependent_type_ids(t)

        elif complex_type.variant == TypeVariant.IPARAM and complex_type.iparam_type:
            deps |= extract_dependent_type_ids(complex_type.iparam_type)

        return deps

    for (module_name,types) in all_types.items():
        for t in types:
            type_id = f"{t.module_name}:{t.type_name}"
            G.add_node(
                t.id,code=t.raw_code
            )

            for constructor_name, fields in t.cons.items():
                constructor_id = f"{type_id}.{constructor_name}"
                G.add_node(constructor_id, type="constructor", belongs_to=type_id)
                G.add_edge(type_id, constructor_id, label="DECLARES")

                for field in fields:
                    field_id = f"{constructor_id}.{field.field_name}"
                    G.add_node(field_id, type="field", field_name=field.field_name)
                    G.add_edge(constructor_id, field_id, label="HAS_FIELD")

                    deps = extract_dependent_type_ids(field.field_type.structure)
                    for dep in deps:
                        if dep != type_id:
                            G.add_edge(field_id, dep, label="USES_TYPE")

    with open(f"{pickle_file_path_with_name}_graph.pkl", "wb") as f:
        pickle.dump(G, f)