from typing import Iterable, Set, Dict, List
import networkx as nx
from code_as_data.models import *
from code_as_data.models.function_model import Function, WhereFunction
from code_as_data.models.type_model import ComplexType, Type, TypeVariant
from code_as_data.models.import_model import Import
from code_as_data.models.class_model import Class
from code_as_data.models.instance_model import Instance


class NetworkxAdapter:
    def __init__(
        self,
        instances_by_module,
        types_by_module,
        imports_by_module,
        functions_by_module,
        classes_by_module,
    ):
        self.instances_by_module: Dict[str, List[Instance]] = instances_by_module
        self.types_by_module: Dict[str, List[Type]] = types_by_module
        self.imports_by_module: Dict[str, List[Import]] = imports_by_module
        self.functions_by_module: Dict[str, List[Function]] = functions_by_module
        self.classes_by_module: Dict[str, List[Class]] = classes_by_module
        self.G = nx.DiGraph()

    def get_graph_object(self):
        return self.G

    def build_function_graph(
        self,
        all_functions: Dict[str, List[Function]],
        all_instances: Dict[str, List[Instance]],
    ) -> nx.DiGraph:

        def add_call_edges(source_func: Function):
            source_id = f"{source_func.module_name}:{source_func.function_name}"
            for called in source_func.functions_called:
                target_id = f"{called.module_name}:{called.function_name}"
                self.G.add_edge(source_id, target_id, type="calls")

        def traverse_where_functions(
            source_func: Function | WhereFunction, parent_id: str
        ):
            for called in source_func.functions_called:
                if not called.module_name or not called.function_name:
                    continue
                called_id = f"{called.module_name}:{called.function_name}"
                self.G.add_edge(parent_id, called_id, type="calls")

            for _, where_func in source_func.where_functions.items():
                where_id = f"{parent_id}.{where_func.function_name}"
                self.G.add_node(where_id, type="where_function")
                self.G.add_edge(parent_id, where_id, type="where")
                traverse_where_functions(where_func, where_id)

        def handle_instances_used(source_func: Function):
            source_id = f"{source_func.module_name}:{source_func.function_name}"
            for instance_sig in list(set(source_func.instances_used)) or []:
                for inst_module, instances in all_instances.items():
                    for inst_obj in instances:
                        if instance_sig == inst_obj.instance_signature:
                            if not inst_obj:
                                continue
                            inst_id = f"{inst_module}:{instance_sig}"
                            if not self.G.has_node(inst_id):
                                self.G.add_node(inst_id, type="instance", label=instance_sig)
                            self.G.add_edge(source_id, inst_id, type="uses_instance")
                            for fn in inst_obj.functions:
                                fn_id = f"{fn.module_name}:{fn.function_name}"
                                if not self.G.has_node(fn_id):
                                    self.G.add_node(fn_id, type="function", label=fn.function_name)
                                self.G.add_edge(inst_id, fn_id, type="instance_defines")
                                traverse_where_functions(fn, fn_id)

        for mod_name, functions in all_functions.items():
            for fn in functions:
                fn_id = f"{mod_name}:{fn.function_name}"
                attrs = dict(
                    label=fn.function_name,
                    node_type="Function",
                    function_signature=fn.function_signature,
                    code_string=fn.raw_string,
                    src_loc=fn.src_loc,
                    line_number_start=fn.line_number_start,
                    line_number_end=fn.line_number_end,
                )
                if not self.G.has_node(fn_id):
                    self.G.add_node(fn_id, **attrs)
                else:
                    self.G.nodes[fn_id].update(attrs)
                add_call_edges(fn)
                traverse_where_functions(fn, fn_id)
                handle_instances_used(fn)

    def extract_dependent_type_ids(self, complex_type: ComplexType) -> Set[str]:
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
                    deps |= self.extract_dependent_type_ids(t)

        elif complex_type.variant in {TypeVariant.APP}:
            if complex_type.app_func:
                deps |= self.extract_dependent_type_ids(complex_type.app_func)
            if complex_type.app_args:
                for arg in complex_type.app_args:
                    deps |= self.extract_dependent_type_ids(arg)

        elif complex_type.variant in {TypeVariant.FUNC}:
            if complex_type.func_arg:
                deps |= self.extract_dependent_type_ids(complex_type.func_arg)
            if complex_type.func_result:
                deps |= self.extract_dependent_type_ids(complex_type.func_result)

        elif complex_type.variant in {TypeVariant.FORALL}:
            if complex_type.forall_body:
                deps |= self.extract_dependent_type_ids(complex_type.forall_body)

        elif complex_type.variant in {TypeVariant.QUAL}:
            if complex_type.qual_context:
                for ctx in complex_type.qual_context:
                    deps |= self.extract_dependent_type_ids(ctx)
            if complex_type.qual_body:
                deps |= self.extract_dependent_type_ids(complex_type.qual_body)

        elif (
            complex_type.variant in {TypeVariant.RECORD} and complex_type.record_fields
        ):
            for _, field_type in complex_type.record_fields:
                deps |= self.extract_dependent_type_ids(field_type)

        elif complex_type.variant in {TypeVariant.TUPLE, TypeVariant.PROMOTED_TUPLE}:
            if complex_type.tuple_types:
                for t in complex_type.tuple_types:
                    deps |= self.extract_dependent_type_ids(t)

        elif complex_type.variant in {TypeVariant.PROMOTED_LIST}:
            if complex_type.promoted_list_types:
                for t in complex_type.promoted_list_types:
                    deps |= self.extract_dependent_type_ids(t)

        elif complex_type.variant == TypeVariant.IPARAM and complex_type.iparam_type:
            deps |= self.extract_dependent_type_ids(complex_type.iparam_type)

        return deps

    def build_type_dependency_graph(self, types:list[Type]):
        for t in types:
            type_id = f"{t.module_name}:{t.type_name}"
            attrs = {
                "node_type": "Type",
                "code_string": t.raw_code,
                "src_loc": t.src_loc,
                "line_number_start": t.line_number_start,
                "line_number_end": t.line_number_end,
            }
            self.G.add_node(type_id, **attrs)
            self.G.nodes[type_id].update(attrs)

            for constructor_name, fields in t.cons.items():
                constructor_id = f"{type_id}.{constructor_name}"
                self.G.add_node(constructor_id, type="constructor", belongs_to=type_id)
                self.G.nodes[constructor_id].update({"type":"constructor", "belongs_to": type_id})
                self.G.add_edge(type_id, constructor_id, label="DECLARES")

                for field in fields:
                    field_id = f"{constructor_id}.{field.field_name}"
                    field_attrs = {"type":"field", "field_name": field.field_name}
                    self.G.add_node(field_id, **field_attrs)
                    self.G.nodes[field_id].update(field_attrs)
                    self.G.add_edge(constructor_id, field_id, label="HAS_FIELD")

                    deps = self.extract_dependent_type_ids(field.field_type.structure)
                    for dep in deps:
                        if dep != type_id:
                            self.G.add_edge(field_id, dep, label="USES_TYPE")

    def process_module(self, module_name):
        self.build_type_dependency_graph(self.types_by_module.get(module_name, []))

        for class_list in self.classes_by_module.get(module_name, []):
            for clas in class_list:
                if isinstance(clas, Class):
                    attrs = {
                        "node_type": "Class",
                        "code_string": clas.class_definition,
                        "src_loc": clas.src_loc,
                        "line_number_start": clas.line_number_start,
                        "line_number_end": clas.line_number_end,
                    }
                    self.G.add_node(clas.id, **attrs)
                    self.G.nodes[clas.id].update(attrs)


    def construct(self):
        for i in set(
            (
                list(self.instances_by_module.keys())
                + list(self.classes_by_module.keys())
                + list(self.functions_by_module.keys())
                + list(self.types_by_module.keys())
                + list(self.imports_by_module.keys())
            )
        ):
            self.process_module(i)
        self.build_function_graph(self.functions_by_module, self.instances_by_module)