from dataclasses import dataclass
import os
import hashlib
from typing import Dict, List, Set, Any

from code_as_data.db.neo4j_connection import Neo4jConnection
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


def create_constraints():
    """Create unique constraints and indexes in Neo4j."""
    print("Creating constraints and indexes...")
    queries = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Module) REQUIRE m.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Package) REQUIRE p.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (f:Function) REQUIRE f.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Instance) REQUIRE i.id IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (i:Instance) ON (i.instance_signature)",  # For USES_INSTANCE_SIGNATURE
        "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Type) REQUIRE t.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (ir:ImportRecord) REQUIRE ir.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (ctor:Constructor) REQUIRE ctor.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (fld:Field) REQUIRE fld.id IS UNIQUE",
    ]
    for query in queries:
        Neo4jConnection.execute_query(query)
    print("Constraints and indexes created successfully.")


def ingest_modules(module_names: Set[str]):
    print(f"Ingesting {len(module_names)} modules...")
    for name in module_names:
        if name:  # Ensure module name is not empty
            Neo4jConnection.execute_query(
                "MERGE (m:Module {name: $name})", parameters={"name": name}
            )
    print("Modules ingestion complete.")


def ingest_classes(all_classes: Dict[str, List[Class]]):
    print(f"Ingesting classes from {len(all_classes)} modules...")
    count = 0
    for module_name, classes_in_module in all_classes.items():
        for cls in classes_in_module:
            if not cls.id:
                print(
                    f"Skipping class with no ID in module {module_name}: {cls.class_name}"
                )
                continue
            Neo4jConnection.execute_query(
                """
                MERGE (c:Class {id: $id})
                ON CREATE SET
                    c.name = $name,
                    c.module_name = $module_name,
                    c.definition = $definition,
                    c.src_location = $src_location,
                    c.line_start = $line_start,
                    c.line_end = $line_end
                ON MATCH SET
                    c.name = $name,
                    c.module_name = $module_name,
                    c.definition = $definition,
                    c.src_location = $src_location,
                    c.line_start = $line_start,
                    c.line_end = $line_end
                WITH c
                MATCH (m:Module {name: $module_name})
                MERGE (c)-[:DEFINED_IN]->(m)
                MERGE (m)-[:HAS_CLASS]->(c)
                """,
                parameters={
                    "id": cls.id,
                    "name": cls.class_name,
                    "module_name": cls.module_name,
                    "definition": cls.class_definition,
                    "src_location": cls.src_location,
                    "line_start": cls.line_number_start,
                    "line_end": cls.line_number_end,
                },
            )
            count += 1
    print(f"Ingested {count} classes.")


def collect_type_data(all_types: Dict[str, List[Type]]):
    types = []
    type_module_links = []
    constructors = []
    fields = []

    for module_name, type_list in all_types.items():
        for type_obj in type_list:
            if not type_obj.id:
                print(
                    f"Skipping type with no ID in module {module_name}: {type_obj.type_name}"
                )
                continue

            # Type node
            types.append(
                {
                    "id": type_obj.id,
                    "name": type_obj.type_name,
                    "module_name": type_obj.module_name,
                    "type_kind": type_obj.type.value,
                    "raw_code": type_obj.raw_code,
                    "src_loc": type_obj.src_loc,
                    "line_start": type_obj.line_number_start,
                    "line_end": type_obj.line_number_end,
                }
            )

            type_module_links.append(
                {"id": type_obj.id, "module_name": type_obj.module_name}
            )

            for con_name, fields_list in type_obj.cons.items():
                ctor_id = f"{type_obj.id}:{con_name}"
                constructors.append(
                    {"id": ctor_id, "name": con_name, "type_id": type_obj.id}
                )

                for field in fields_list:
                    field_id = f"{ctor_id}:{field.field_name}"
                    field_props = {
                        "id": field_id,
                        "name": field.field_name,
                        "constructor_id": ctor_id,
                        "raw_type_code": field.field_type.raw_code,
                        "type_variant": field.field_type.structure.variant.value,
                    }
                    if field.field_type.structure.variant.name == "ATOMIC":
                        ac = field.field_type.structure.atomic_component
                        if ac:
                            field_props.update(
                                {
                                    "atomic_type_name": ac.type_name,
                                    "atomic_module_name": ac.module_name,
                                    "atomic_package_name": ac.package_name,
                                }
                            )
                    fields.append(field_props)

    return types, type_module_links, constructors, fields


def ingest_types(all_types: Dict[str, List[Type]]):
    print("Collecting type metadata...")
    types, type_module_links, constructors, fields = collect_type_data(all_types)

    print(
        f"Ingesting {len(types)} types, {len(constructors)} constructors, {len(fields)} fields..."
    )

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MERGE (t:Type {id: row.id})
       ON CREATE SET t += row
       ON MATCH SET t += row",
      {params: {rows: $type_rows}, batchSize: 100}
    )
    """,
        parameters={"type_rows": types},
    )

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (t:Type {id: row.id})
       MATCH (m:Module {name: row.module_name})
       MERGE (t)-[:DEFINED_IN]->(m)
       MERGE (m)-[:HAS_TYPE]->(t)",
      {params: {rows: $link_rows}, batchSize: 100}
    )
    """,
        parameters={"link_rows": type_module_links},
    )

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (t:Type {id: row.type_id})
       MERGE (c:Constructor {id: row.id})
       SET c.name = row.name, c.type_id = row.type_id
       MERGE (t)-[:HAS_CONSTRUCTOR]->(c)",
      {params: {rows: $ctor_rows}, batchSize: 100}
    )
    """,
        parameters={"ctor_rows": constructors},
    )

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (c:Constructor {id: row.constructor_id})
       MERGE (f:Field {id: row.id})
       SET f += row
       MERGE (c)-[:HAS_FIELD]->(f)",
      {params: {rows: $field_rows}, batchSize: 100}
    )
    """,
        parameters={"field_rows": fields},
    )

    print("Done.")


def collect_all_functions(all_functions: Dict[str, List[Function]]):
    all_fn_nodes = []
    fn_module_links = []
    where_links = []

    def collect_fn(fn: Function, module_name: str, is_where: bool):
        if not fn.id:
            print(
                f"Skipping function with no ID in module {module_name}: {fn.function_name}"
            )
            return

        all_fn_nodes.append(
            {
                "id": fn.id,
                "name": fn.function_name,
                "module_name": module_name,
                "signature": fn.function_signature,
                "src_loc": fn.src_loc,
                "raw_string": fn.raw_string,
                "type_enum": fn.type_enum,
                "line_start": fn.line_number_start,
                "line_end": fn.line_number_end,
                "label": "WhereFunction" if is_where else "Function",
            }
        )

        fn_module_links.append({"id": fn.id, "module_name": module_name})

        for where_fn in fn.where_functions.values():
            where_links.append({"parent_id": fn.id, "where_id": where_fn.id})
            collect_fn(where_fn, module_name, is_where=True)

    for module, fns in all_functions.items():
        for fn in fns:
            collect_fn(fn, module, is_where=False)

    return all_fn_nodes, fn_module_links, where_links


def ingest_functions(all_functions: Dict[str, List[Function]]):
    print("Collecting functions...")
    fn_nodes, fn_module_links, where_links = collect_all_functions(all_functions)
    print(f"Ingesting {len(fn_nodes)} function nodes...")

    # Step 1: Insert all functions (using dynamic labels)
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MERGE (f:`Function`) WHERE row.label = 'Function'
       SET f.id = row.id, f.name = row.name, f.module_name = row.module_name,
           f.signature = row.signature, f.src_loc = row.src_loc, f.raw_string = row.raw_string,
           f.type_enum = row.type_enum, f.line_start = row.line_start, f.line_end = row.line_end
       WITH f, row
       CALL apoc.create.addLabels(id(f), [row.label]) YIELD node RETURN node",
      {params: {rows: $function_rows}, batchSize: 100}
    )
    """,
        parameters={"function_rows": fn_nodes},
    )

    # Step 2: Link functions to modules
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (f {id: row.id})
       MATCH (m:Module {name: row.module_name})
       MERGE (f)-[:DEFINED_IN]->(m)
       MERGE (m)-[:HAS_FUNCTION]->(f)",
      {params: {rows: $link_rows}, batchSize: 100}
    )
    """,
        parameters={"link_rows": fn_module_links},
    )

    # Step 3: Link parent to where-functions
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (p:Function {id: row.parent_id})
       MATCH (w:WhereFunction {id: row.where_id})
       MERGE (p)-[:DEFINES_WHERE]->(w)",
      {params: {rows: $where_rows}, batchSize: 100}
    )
    """,
        parameters={"where_rows": where_links},
    )

    print("Function ingestion complete.")


def collect_instance_nodes(all_instances: Dict[str, List[Instance]]):
    instances = []
    links_to_modules = []

    for module_name, instance_list in all_instances.items():
        for inst in instance_list:
            if not inst.id:
                print(
                    f"Skipping instance with no ID in module {module_name}: {inst.instanceDefinition}"
                )
                continue

            instances.append(
                {
                    "id": inst.id,
                    "name": inst.instanceDefinition,
                    "module_name": module_name,
                    "signature": inst.instance_signature,
                    "src_loc": inst.src_loc,
                    "line_start": inst.line_number_start,
                    "line_end": inst.line_number_end,
                }
            )

            links_to_modules.append({"id": inst.id, "module_name": module_name})

    return instances, links_to_modules


def ingest_instances(all_instances: Dict[str, List[Instance]]):
    print("Collecting instance data...")
    instance_nodes, module_links = collect_instance_nodes(all_instances)
    print(f"Ingesting {len(instance_nodes)} instances...")

    # Create or update Instance nodes
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MERGE (i:Instance {id: row.id})
       SET i.name = row.name,
           i.module_name = row.module_name,
           i.instance_signature = row.signature,
           i.src_loc = row.src_loc,
           i.line_start = row.line_start,
           i.line_end = row.line_end",
      {params: {rows: $instance_rows}, batchSize: 100}
    )
    """,
        parameters={"instance_rows": instance_nodes},
    )

    # Create DEFINED_IN and HAS_INSTANCE relationships
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (i:Instance {id: row.id})
       MATCH (m:Module {name: row.module_name})
       MERGE (i)-[:DEFINED_IN]->(m)
       MERGE (m)-[:HAS_INSTANCE]->(i)",
      {params: {rows: $link_rows}, batchSize: 100}
    )
    """,
        parameters={"link_rows": module_links},
    )

    print("Instance ingestion complete.")


def ingest_imports(all_imports: Dict[str, List[Import]]):
    print(f"Ingesting import records from {len(all_imports)} modules...")
    count = 0
    for importer_module_name, imports_in_module in all_imports.items():
        for imp in imports_in_module:
            # Create a unique ID for the ImportRecord node
            # Using a hash of relevant fields to ensure uniqueness and manageability
            id_string = f"{importer_module_name}:{imp.line_number_start}:{imp.module_name or ''}:{imp.package_name or ''}:{imp.as_module_name or ''}"
            import_record_id = hashlib.md5(id_string.encode()).hexdigest()

            Neo4jConnection.execute_query(
                """
                MERGE (ir:ImportRecord {id: $id})
                ON CREATE SET
                    ir.importer_module_name = $importer_module_name,
                    ir.imported_module_name = $imported_module_name,
                    ir.imported_package_name = $imported_package_name,
                    ir.as_module_name = $as_module_name,
                    ir.is_hiding = $is_hiding,
                    ir.hiding_specs = $hiding_specs,
                    ir.is_qualified = $is_qualified,
                    ir.src_loc = $src_loc,
                    ir.line_start = $line_start,
                    ir.line_end = $line_end
                ON MATCH SET
                    ir.importer_module_name = $importer_module_name,
                    ir.imported_module_name = $imported_module_name,
                    ir.imported_package_name = $imported_package_name,
                    ir.as_module_name = $as_module_name,
                    ir.is_hiding = $is_hiding,
                    ir.hiding_specs = $hiding_specs,
                    ir.is_qualified = $is_qualified,
                    ir.src_loc = $src_loc,
                    ir.line_start = $line_start,
                    ir.line_end = $line_end
                WITH ir
                MATCH (m:Module {name: $importer_module_name})
                MERGE (m)-[:DECLARES_IMPORT]->(ir)
                """,
                parameters={
                    "id": import_record_id,
                    "importer_module_name": importer_module_name,
                    "imported_module_name": imp.module_name,
                    "imported_package_name": imp.package_name,
                    "as_module_name": imp.as_module_name,
                    "is_hiding": imp.is_hiding,
                    "hiding_specs": imp.hiding_specs,  # List of strings
                    "is_qualified": imp.qualified_style is not None,
                    "src_loc": imp.src_loc,
                    "line_start": imp.line_number_start,
                    "line_end": imp.line_number_end,
                },
            )
            count += 1
    print(f"Ingested {count} import records.")


# --- Phase 2: Relationship Ingestion ---


def collect_import_links(all_imports: Dict[str, List[Import]]):
    module_imports = []
    package_imports = []
    modules = set()
    packages = set()

    for importer_module, imports in all_imports.items():
        for imp in imports:
            id_string = f"{importer_module}:{imp.line_number_start}:{imp.module_name or ''}:{imp.package_name or ''}:{imp.as_module_name or ''}"
            import_record_id = hashlib.md5(id_string.encode()).hexdigest()

            if imp.module_name:
                modules.add(imp.module_name)
                module_imports.append(
                    {"ir_id": import_record_id, "module_name": imp.module_name}
                )

            if imp.package_name:
                packages.add(imp.package_name)
                package_imports.append(
                    {"ir_id": import_record_id, "package_name": imp.package_name}
                )

    return list(modules), list(packages), module_imports, package_imports


def ingest_import_links(all_imports: Dict[str, List[Import]]):
    print("Collecting import links...")
    module_nodes, package_nodes, mod_links, pkg_links = collect_import_links(
        all_imports
    )
    print(f"Ingesting {len(mod_links)} module links, {len(pkg_links)} package links...")

    # Ensure modules
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $names AS name RETURN name",
      "MERGE (:Module {name: name})",
      {params: {names: $module_names}, batchSize: 100}
    )
    """,
        parameters={"module_names": module_nodes},
    )

    # Ensure packages
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $names AS name RETURN name",
      "MERGE (:Package {name: name})",
      {params: {names: $package_names}, batchSize: 100}
    )
    """,
        parameters={"package_names": package_nodes},
    )

    # ImportRecord → Module
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (ir:ImportRecord {id: row.ir_id})
       MATCH (m:Module {name: row.module_name})
       MERGE (ir)-[:IMPORTS_MODULE]->(m)",
      {params: {rows: $module_links}, batchSize: 100}
    )
    """,
        parameters={"module_links": mod_links},
    )

    # ImportRecord → Package
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (ir:ImportRecord {id: row.ir_id})
       MATCH (p:Package {name: row.package_name})
       MERGE (ir)-[:IMPORTS_PACKAGE]->(p)",
      {params: {rows: $package_links}, batchSize: 100}
    )
    """,
        parameters={"package_links": pkg_links},
    )

    print("Import links ingestion complete.")


def _collect_function_relationships(fn_data: Function, relationships: dict):
    if fn_data.id:
        # Called functions
        for called_fn in fn_data.functions_called:
            if called_fn.id:
                relationships["calls"].append(
                    {"caller_id": fn_data.id, "callee_id": called_fn.id}
                )
                relationships["ensure_functions"].add(
                    (called_fn.id, called_fn.function_name, called_fn.module_name)
                )

        # Where functions
        for _, where_fn in fn_data.where_functions.items():
            if where_fn.id:
                relationships["defines_where"].append(
                    {"parent_id": fn_data.id, "where_id": where_fn.id}
                )
                _collect_function_relationships(where_fn, relationships)

        # Instances used
        for sig in fn_data.instances_used or []:
            if isinstance(sig, str):
                relationships["uses_instance"].append(
                    {"func_id": fn_data.id, "instance_sig": sig}
                )


def ingest_function_relationships(all_functions: Dict[str, List[Function]]):
    print(
        "Ingesting function relationships (CALLS, DEFINES_WHERE, USES_INSTANCE_SIGNATURE)..."
    )
    relationships = {
        "calls": [],
        "defines_where": [],
        "uses_instance": [],
        "ensure_functions": set(),
    }

    print("Collecting function relationships...")
    for functions in all_functions.values():
        for func in functions:
            _collect_function_relationships(func, relationships)

    print("Batch inserting relationships with APOC...")

    # Convert set to list of dicts
    ensure_fn_data = [
        {"id": id_, "name": name, "module_name": mod}
        for (id_, name, mod) in relationships["ensure_functions"]
    ]

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MERGE (f:Function {id: row.id}) ON CREATE SET f.name = row.name, f.module_name = row.module_name",
      {params: {rows: $ensure_rows}, batchSize: 100}
    )""",
        parameters={"ensure_rows": ensure_fn_data},
    )

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (caller:Function {id: row.caller_id}) MATCH (callee:Function {id: row.callee_id}) MERGE (caller)-[:CALLS]->(callee)",
      {params: {rows: $call_rows}, batchSize: 100}
    )""",
        parameters={"call_rows": relationships["calls"]},
    )

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (p:Function {id: row.parent_id}) MATCH (w:WhereFunction {id: row.where_id}) MERGE (p)-[:DEFINES_WHERE]->(w)",
      {params: {rows: $dw_rows}, batchSize: 100}
    )""",
        parameters={"dw_rows": relationships["defines_where"]},
    )

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (f:Function {id: row.func_id}) MATCH (i:Instance {instance_signature: row.instance_sig}) MERGE (f)-[:USES_INSTANCE_SIGNATURE]->(i)",
      {params: {rows: $ui_rows}, batchSize: 100}
    )""",
        parameters={"ui_rows": relationships["uses_instance"]},
    )

    print("Function relationships ingestion complete.")


def collect_instance_relationships(all_instances: Dict[str, List[Instance]]):
    implements_rels = []
    for module, instances in all_instances.items():
        for inst in instances:
            if not inst.id:
                continue
            for fn in inst.functions:
                if fn.id:
                    implements_rels.append({"instance_id": inst.id, "func_id": fn.id})
    return implements_rels


def ingest_instance_relationships(all_instances: Dict[str, List[Instance]]):
    print("Collecting IMPLEMENTS relationships...")
    rels = collect_instance_relationships(all_instances)
    print(f"Ingesting {len(rels)} IMPLEMENTS relationships...")

    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (i:Instance {id: row.instance_id})
       MATCH (f:Function {id: row.func_id})
       MERGE (i)-[:IMPLEMENTS]->(f)",
      {params: {rows: $rels}, batchSize: 100}
    )
    """,
        parameters={"rels": rels},
    )

    print("IMPLEMENTS relationships ingested.")


@dataclass
class TypeReference:
    """Represents a reference to a type with context about where it's used."""

    source_field_id: str
    target_type_id: str
    target_type_name: str
    target_module_name: str
    relationship_type: str  # 'atomic', 'list_element', 'tuple_element', 'function_arg', 'function_result', etc.
    depth: int = 0  # How deeply nested this reference is


@dataclass
class ComplexTypeRelationship:
    """Represents a complex relationship between types."""

    source_field_id: str
    relationship_type: str
    structure_info: Dict[str, Any]


def collect_field_type_relationships(all_types: Dict[str, List[Type]]):
    """
    Extended version that collects all type relationships, not just atomic ones.

    Returns:
        - ensure_type_list: List of all referenced types that should exist
        - type_references: List of all type references with their context
        - complex_relationships: List of complex type relationships (functions, applications, etc.)
    """
    type_references = []
    complex_relationships = []
    ensure_type_nodes = set()

    def extract_type_references(
        complex_type: ComplexType, source_field_id: str, depth: int = 0
    ) -> None:
        """Recursively extract all type references from a complex type structure."""

        if complex_type.variant == TypeVariant.ATOMIC and complex_type.atomic_component:
            # Handle atomic types
            ac = complex_type.atomic_component
            target_id = f"{ac.module_name}:{ac.type_name}"
            type_references.append(
                TypeReference(
                    source_field_id=source_field_id,
                    target_type_id=target_id,
                    target_type_name=ac.type_name,
                    target_module_name=ac.module_name,
                    relationship_type="atomic",
                    depth=depth,
                )
            )
            ensure_type_nodes.add((target_id, ac.type_name, ac.module_name))

        elif complex_type.variant == TypeVariant.LIST and complex_type.list_type:
            # Handle list types [a]
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="list",
                    structure_info={"depth": depth},
                )
            )
            extract_type_references(complex_type.list_type, source_field_id, depth + 1)

        elif complex_type.variant == TypeVariant.TUPLE and complex_type.tuple_types:
            # Handle tuple types (a, b, c)
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="tuple",
                    structure_info={
                        "arity": len(complex_type.tuple_types),
                        "depth": depth,
                    },
                )
            )
            for i, tuple_type in enumerate(complex_type.tuple_types):
                extract_type_references(
                    tuple_type, f"{source_field_id}[tuple_{i}]", depth + 1
                )

        elif (
            complex_type.variant == TypeVariant.APP
            and complex_type.app_func
            and complex_type.app_args
        ):
            # Handle type applications like Maybe a, Either a b
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="type_application",
                    structure_info={
                        "arity": len(complex_type.app_args),
                        "depth": depth,
                    },
                )
            )
            extract_type_references(
                complex_type.app_func, f"{source_field_id}[app_func]", depth + 1
            )
            for i, arg_type in enumerate(complex_type.app_args):
                extract_type_references(
                    arg_type, f"{source_field_id}[app_arg_{i}]", depth + 1
                )

        elif (
            complex_type.variant == TypeVariant.FUNC
            and complex_type.func_arg
            and complex_type.func_result
        ):
            # Handle function types a -> b
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="function",
                    structure_info={"depth": depth},
                )
            )
            extract_type_references(
                complex_type.func_arg, f"{source_field_id}[func_arg]", depth + 1
            )
            extract_type_references(
                complex_type.func_result, f"{source_field_id}[func_result]", depth + 1
            )

        elif (
            complex_type.variant == TypeVariant.FORALL
            and complex_type.forall_binders
            and complex_type.forall_body
        ):
            # Handle forall types forall a. a -> a
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="forall",
                    structure_info={
                        "binders": [b.type_name for b in complex_type.forall_binders],
                        "depth": depth,
                    },
                )
            )
            extract_type_references(
                complex_type.forall_body, f"{source_field_id}[forall_body]", depth + 1
            )

        elif (
            complex_type.variant == TypeVariant.QUAL
            and complex_type.qual_context
            and complex_type.qual_body
        ):
            # Handle qualified types like (Show a, Eq a) => a -> String
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="qualified",
                    structure_info={
                        "context_count": len(complex_type.qual_context),
                        "depth": depth,
                    },
                )
            )
            for i, context_type in enumerate(complex_type.qual_context):
                extract_type_references(
                    context_type, f"{source_field_id}[qual_context_{i}]", depth + 1
                )
            extract_type_references(
                complex_type.qual_body, f"{source_field_id}[qual_body]", depth + 1
            )

        elif (
            complex_type.variant == TypeVariant.KIND_SIG
            and complex_type.kind_type
            and complex_type.kind_sig
        ):
            # Handle kind signatures
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="kind_signature",
                    structure_info={"depth": depth},
                )
            )
            extract_type_references(
                complex_type.kind_type, f"{source_field_id}[kind_type]", depth + 1
            )
            extract_type_references(
                complex_type.kind_sig, f"{source_field_id}[kind_sig]", depth + 1
            )

        elif complex_type.variant == TypeVariant.BANG and complex_type.bang_type:
            # Handle strict types !a
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="strict",
                    structure_info={"depth": depth},
                )
            )
            extract_type_references(
                complex_type.bang_type, f"{source_field_id}[bang]", depth + 1
            )

        elif complex_type.variant == TypeVariant.RECORD and complex_type.record_fields:
            # Handle record types { field1 :: a, field2 :: b }
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="record",
                    structure_info={
                        "field_count": len(complex_type.record_fields),
                        "field_names": [
                            field[0] for field in complex_type.record_fields
                        ],
                        "depth": depth,
                    },
                )
            )
            for field_name, field_type in complex_type.record_fields:
                extract_type_references(
                    field_type, f"{source_field_id}[record_{field_name}]", depth + 1
                )

        elif (
            complex_type.variant == TypeVariant.PROMOTED_LIST
            and complex_type.promoted_list_types
        ):
            # Handle promoted list types '[a, b, c]
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="promoted_list",
                    structure_info={
                        "element_count": len(complex_type.promoted_list_types),
                        "depth": depth,
                    },
                )
            )
            for i, elem_type in enumerate(complex_type.promoted_list_types):
                extract_type_references(
                    elem_type, f"{source_field_id}[promoted_list_{i}]", depth + 1
                )

        elif (
            complex_type.variant == TypeVariant.PROMOTED_TUPLE
            and complex_type.tuple_types
        ):
            # Handle promoted tuple types '(a, b, c)
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="promoted_tuple",
                    structure_info={
                        "arity": len(complex_type.tuple_types),
                        "depth": depth,
                    },
                )
            )
            for i, tuple_type in enumerate(complex_type.tuple_types):
                extract_type_references(
                    tuple_type, f"{source_field_id}[promoted_tuple_{i}]", depth + 1
                )

        elif complex_type.variant == TypeVariant.IPARAM and complex_type.iparam_type:
            # Handle implicit parameters ?x :: a
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="implicit_parameter",
                    structure_info={
                        "param_name": complex_type.iparam_name,
                        "depth": depth,
                    },
                )
            )
            extract_type_references(
                complex_type.iparam_type, f"{source_field_id}[iparam]", depth + 1
            )

        elif complex_type.variant == TypeVariant.DOC and complex_type.doc_type:
            # Handle documented types
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="documented",
                    structure_info={
                        "doc_string": complex_type.doc_string,
                        "depth": depth,
                    },
                )
            )
            extract_type_references(
                complex_type.doc_type, f"{source_field_id}[doc]", depth + 1
            )

        elif complex_type.variant == TypeVariant.LITERAL:
            # Handle literal types
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type="literal",
                    structure_info={
                        "literal_value": complex_type.literal_value,
                        "depth": depth,
                    },
                )
            )

        elif complex_type.variant in [TypeVariant.WILDCARD, TypeVariant.STAR]:
            # Handle wildcards and star kinds
            complex_relationships.append(
                ComplexTypeRelationship(
                    source_field_id=source_field_id,
                    relationship_type=complex_type.variant.value.lower(),
                    structure_info={"depth": depth},
                )
            )

    # Process all types and their fields
    for module, type_list in all_types.items():
        for typ in type_list:
            if not typ.id:
                continue
            for con_name, fields in typ.cons.items():
                ctor_id = f"{typ.id}:{con_name}"
                for field in fields:
                    field_id = f"{ctor_id}:{field.field_name}"
                    extract_type_references(field.field_type.structure, field_id)

    # Create the ensure_type_list from collected nodes
    ensure_type_list = [
        {"id": id_, "name": name, "module_name": mod}
        for (id_, name, mod) in ensure_type_nodes
    ]

    return ensure_type_list, type_references, complex_relationships


def analyze_type_complexity(
    type_references: List[TypeReference],
    complex_relationships: List[ComplexTypeRelationship],
) -> Dict[str, Any]:
    """
    Analyze the complexity of type relationships.

    Returns statistics about the type usage patterns.
    """
    stats = {
        "total_type_references": len(type_references),
        "total_complex_relationships": len(complex_relationships),
        "max_nesting_depth": max((ref.depth for ref in type_references), default=0),
        "relationship_counts": {},
        "most_referenced_types": {},
        "nesting_distribution": {},
        "module_dependencies": set(),
    }

    # Count relationship types
    for rel in complex_relationships:
        rel_type = rel.relationship_type
        stats["relationship_counts"][rel_type] = (
            stats["relationship_counts"].get(rel_type, 0) + 1
        )

    # Count type references
    for ref in type_references:
        type_name = ref.target_type_name
        stats["most_referenced_types"][type_name] = (
            stats["most_referenced_types"].get(type_name, 0) + 1
        )

        # Track nesting depth distribution
        depth = ref.depth
        stats["nesting_distribution"][depth] = (
            stats["nesting_distribution"].get(depth, 0) + 1
        )

        # Track module dependencies
        if ref.target_module_name:
            stats["module_dependencies"].add(ref.target_module_name)

    # Convert set to list for JSON serialization
    stats["module_dependencies"] = list(stats["module_dependencies"])

    # Sort most referenced types
    stats["most_referenced_types"] = dict(
        sorted(stats["most_referenced_types"].items(), key=lambda x: x[1], reverse=True)
    )

    return stats


def ingest_field_type_relationships_apoc(all_types: Dict[str, List[Type]]):
    print("Collecting HAS_ATOMIC_TYPE relationships...")
    ensure_nodes, type_rels = collect_field_type_relationships(all_types)
    print(f"Ensuring {len(ensure_nodes)} Type nodes...")
    print(f"Ingesting {len(type_rels)} HAS_ATOMIC_TYPE relationships...")

    # Ensure referenced Type nodes exist
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MERGE (t:Type {id: row.id})
       ON CREATE SET t.name = row.name, t.module_name = row.module_name",
      {params: {rows: $type_nodes}, batchSize: 100}
    )
    """,
        parameters={"type_nodes": ensure_nodes},
    )

    # Create HAS_ATOMIC_TYPE edges
    Neo4jConnection.execute_query(
        """
    CALL apoc.periodic.iterate(
      "UNWIND $rows AS row RETURN row",
      "MATCH (f:Field {id: row.field_id})
       MATCH (t:Type {id: row.target_type_id})
       MERGE (f)-[:HAS_ATOMIC_TYPE]->(t)",
      {params: {rows: $rels}, batchSize: 100}
    )
    """,
        parameters={"rels": type_rels},
    )

    print("HAS_ATOMIC_TYPE relationships ingested.")
