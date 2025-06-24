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
        "CREATE INDEX IF NOT EXISTS FOR (i:Instance) ON (i.instance_signature)", # For USES_INSTANCE_SIGNATURE
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
        if name: # Ensure module name is not empty
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
                print(f"Skipping class with no ID in module {module_name}: {cls.class_name}")
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
            count +=1
    print(f"Ingested {count} classes.")

def ingest_types(all_types: Dict[str, List[Type]]):
    print(f"Ingesting types from {len(all_types)} modules...")
    type_count = 0
    constructor_count = 0
    field_count = 0

    for module_name, types_in_module in all_types.items():
        for type_obj in types_in_module:
            if not type_obj.id:
                print(f"Skipping type with no ID in module {module_name}: {type_obj.type_name}")
                continue
            Neo4jConnection.execute_query(
                """
                MERGE (t:Type {id: $id})
                ON CREATE SET
                    t.name = $name,
                    t.module_name = $module_name,
                    t.type_kind = $type_kind,
                    t.raw_code = $raw_code,
                    t.src_loc = $src_loc,
                    t.line_start = $line_start,
                    t.line_end = $line_end
                ON MATCH SET
                    t.name = $name,
                    t.module_name = $module_name,
                    t.type_kind = $type_kind,
                    t.raw_code = $raw_code,
                    t.src_loc = $src_loc,
                    t.line_start = $line_start,
                    t.line_end = $line_end
                WITH t
                MATCH (m:Module {name: $module_name})
                MERGE (t)-[:DEFINED_IN]->(m)
                MERGE (m)-[:HAS_TYPE]->(t)
                """,
                parameters={
                    "id": type_obj.id,
                    "name": type_obj.type_name,
                    "module_name": type_obj.module_name,
                    "type_kind": type_obj.type.value,
                    "raw_code": type_obj.raw_code,
                    "src_loc": type_obj.src_loc,
                    "line_start": type_obj.line_number_start,
                    "line_end": type_obj.line_number_end,
                },
            )
            type_count += 1

            for con_name, fields in type_obj.cons.items():
                constructor_id = f"{type_obj.id}:{con_name}"
                Neo4jConnection.execute_query(
                    """
                    MATCH (t:Type {id: $type_id})
                    MERGE (ctor:Constructor {id: $ctor_id})
                    ON CREATE SET ctor.name = $ctor_name, ctor.type_id = $type_id
                    ON MATCH SET ctor.name = $ctor_name, ctor.type_id = $type_id
                    MERGE (t)-[:HAS_CONSTRUCTOR]->(ctor)
                    """,
                    parameters={
                        "type_id": type_obj.id,
                        "ctor_id": constructor_id,
                        "ctor_name": con_name,
                    },
                )
                constructor_count += 1

                for field in fields:
                    field_id = f"{constructor_id}:{field.field_name}"
                    # Basic field properties
                    field_props = {
                        "name": field.field_name,
                        "constructor_id": constructor_id,
                        "raw_type_code": field.field_type.raw_code,
                        "type_variant": field.field_type.structure.variant.value
                    }
                    # Add specific properties for atomic types if available
                    if field.field_type.structure.variant == TypeVariant.ATOMIC and \
                       field.field_type.structure.atomic_component:
                        field_props["atomic_type_name"] = field.field_type.structure.atomic_component.type_name
                        field_props["atomic_module_name"] = field.field_type.structure.atomic_component.module_name
                        field_props["atomic_package_name"] = field.field_type.structure.atomic_component.package_name


                    Neo4jConnection.execute_query(
                        """
                        MATCH (ctor:Constructor {id: $ctor_id})
                        MERGE (fld:Field {id: $field_id})
                        ON CREATE SET fld = $props
                        ON MATCH SET fld = $props
                        MERGE (ctor)-[:HAS_FIELD]->(fld)
                        """,
                        parameters={
                            "ctor_id": constructor_id,
                            "field_id": field_id,
                            "props": field_props
                        },
                    )
                    field_count += 1
    print(f"Ingested {type_count} types, {constructor_count} constructors, and {field_count} fields.")


def _ingest_single_function_data(fn_data: Function, module_name: str, is_where_function: bool = False):
    if not fn_data.id:
        print(f"Skipping function with no ID in module {module_name}: {fn_data.function_name}")
        return

    label = "WhereFunction" if is_where_function else "Function"
    
    Neo4jConnection.execute_query(
        f"""
        MERGE (f:{label} {{id: $id}})
        ON CREATE SET
            f.name = $name,
            f.module_name = $module_name,
            f.signature = $signature,
            f.src_loc = $src_loc,
            f.raw_string = $raw_string,
            f.type_enum = $type_enum,
            f.line_start = $line_start,
            f.line_end = $line_end
        ON MATCH SET
            f.name = $name,
            f.module_name = $module_name,
            f.signature = $signature,
            f.src_loc = $src_loc,
            f.raw_string = $raw_string,
            f.type_enum = $type_enum,
            f.line_start = $line_start,
            f.line_end = $line_end
        WITH f
        MATCH (m:Module {{name: $module_name}})
        MERGE (f)-[:DEFINED_IN]->(m)
        MERGE (m)-[:HAS_FUNCTION]->(f) 
        """, # HAS_FUNCTION might be broad if it includes WhereFunctions; consider HAS_TOP_LEVEL_FUNCTION vs HAS_WHERE_FUNCTION
        parameters={
            "id": fn_data.id,
            "name": fn_data.function_name,
            "module_name": module_name, # fn_data.module_name should be same
            "signature": fn_data.function_signature,
            "src_loc": fn_data.src_loc,
            "raw_string": fn_data.raw_string,
            "type_enum": fn_data.type_enum,
            "line_start": fn_data.line_number_start,
            "line_end": fn_data.line_number_end,
        },
    )

    # Recursively ingest where_functions
    for where_fn_name, where_fn_obj in fn_data.where_functions.items():
        # where_fn_obj is WhereFunction, which is a Function model
        _ingest_single_function_data(where_fn_obj, module_name, is_where_function=True)


def ingest_functions(all_functions: Dict[str, List[Function]]):
    print(f"Ingesting functions from {len(all_functions)} modules...")
    count = 0
    for module_name, functions_in_module in all_functions.items():
        for func in functions_in_module:
            _ingest_single_function_data(func, module_name)
            count +=1 # Counts top-level functions; where_functions are counted recursively
    print(f"Ingested {count} top-level functions (where_functions ingested recursively).")


def ingest_instances(all_instances: Dict[str, List[Instance]]):
    print(f"Ingesting instances from {len(all_instances)} modules...")
    count = 0
    for module_name, instances_in_module in all_instances.items():
        for inst in instances_in_module:
            if not inst.id:
                print(f"Skipping instance with no ID in module {module_name}: {inst.instanceDefinition}")
                continue
            Neo4jConnection.execute_query(
                """
                MERGE (i:Instance {id: $id})
                ON CREATE SET
                    i.name = $name,
                    i.module_name = $module_name,
                    i.instance_signature = $signature,
                    i.src_loc = $src_loc,
                    i.line_start = $line_start,
                    i.line_end = $line_end
                ON MATCH SET
                    i.name = $name,
                    i.module_name = $module_name,
                    i.instance_signature = $signature,
                    i.src_loc = $src_loc,
                    i.line_start = $line_start,
                    i.line_end = $line_end
                WITH i
                MATCH (m:Module {name: $module_name})
                MERGE (i)-[:DEFINED_IN]->(m)
                MERGE (m)-[:HAS_INSTANCE]->(i)
                """,
                parameters={
                    "id": inst.id,
                    "name": inst.instanceDefinition,
                    "module_name": inst.module_name,
                    "signature": inst.instance_signature,
                    "src_loc": inst.src_loc,
                    "line_start": inst.line_number_start,
                    "line_end": inst.line_number_end,
                },
            )
            count += 1
    print(f"Ingested {count} instances.")

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
                    "hiding_specs": imp.hiding_specs, # List of strings
                    "is_qualified": imp.qualified_style is not None,
                    "src_loc": imp.src_loc,
                    "line_start": imp.line_number_start,
                    "line_end": imp.line_number_end,
                },
            )
            count += 1
    print(f"Ingested {count} import records.")


# --- Phase 2: Relationship Ingestion ---

def ingest_import_links(all_imports: Dict[str, List[Import]]):
    print("Ingesting import links (ImportRecord -> Module/Package)...")
    count = 0
    for importer_module_name, imports_in_module in all_imports.items():
        for imp in imports_in_module:
            id_string = f"{importer_module_name}:{imp.line_number_start}:{imp.module_name or ''}:{imp.package_name or ''}:{imp.as_module_name or ''}"
            import_record_id = hashlib.md5(id_string.encode()).hexdigest()

            if imp.module_name:
                # Ensure the target module exists (it should if all modules were pre-ingested)
                Neo4jConnection.execute_query("MERGE (m:Module {name: $name})", parameters={"name": imp.module_name})
                Neo4jConnection.execute_query(
                    """
                    MATCH (ir:ImportRecord {id: $ir_id})
                    MATCH (m:Module {name: $imported_module_name})
                    MERGE (ir)-[:IMPORTS_MODULE]->(m)
                    """,
                    parameters={
                        "ir_id": import_record_id,
                        "imported_module_name": imp.module_name,
                    },
                )
                count +=1
            
            if imp.package_name:
                Neo4jConnection.execute_query("MERGE (p:Package {name: $name})", parameters={"name": imp.package_name})
                Neo4jConnection.execute_query(
                    """
                    MATCH (ir:ImportRecord {id: $ir_id})
                    MATCH (p:Package {name: $package_name})
                    MERGE (ir)-[:IMPORTS_PACKAGE]->(p)
                    """,
                    parameters={
                        "ir_id": import_record_id,
                        "package_name": imp.package_name,
                    },
                )
                count +=1 # Counts relationships
    print(f"Ingested {count} import links to modules/packages.")


def _ingest_function_relationships_recursive(fn_data: Function, current_module_name: str):
    # Called functions
    for called_fn_data in fn_data.functions_called:
        if called_fn_data.id and fn_data.id: # Ensure both caller and callee have IDs
            # Callee might be in a different module, ensure it exists
            # The FunctionCalled model has module_name and function_name, so its id is module:func
            Neo4jConnection.execute_query(
                # Ensure callee function node exists (might be from a different module)
                # This MERGE is a safeguard; ideally, all functions are pre-ingested.
                "MERGE (f_callee:Function {id: $callee_id}) ON CREATE SET f_callee.name = $callee_name, f_callee.module_name = $callee_module_name",
                parameters={
                    "callee_id": called_fn_data.id, 
                    "callee_name": called_fn_data.function_name,
                    "callee_module_name": called_fn_data.module_name
                }
            )
            Neo4jConnection.execute_query(
                """
                MATCH (caller {id: $caller_id})
                MATCH (callee:Function {id: $callee_id})
                MERGE (caller)-[:CALLS]->(callee)
                """,
                parameters={"caller_id": fn_data.id, "callee_id": called_fn_data.id},
            )

    # Where functions definitions
    for where_fn_name, where_fn_obj in fn_data.where_functions.items():
        if where_fn_obj.id and fn_data.id:
            Neo4jConnection.execute_query(
                """
                MATCH (parent_f {id: $parent_id})
                MATCH (where_f:WhereFunction {id: $where_id})
                MERGE (parent_f)-[:DEFINES_WHERE]->(where_f)
                """,
                parameters={"parent_id": fn_data.id, "where_id": where_fn_obj.id},
            )
            # Recursively process relationships for this where_function
            _ingest_function_relationships_recursive(where_fn_obj, current_module_name)

    # Instances used
    if fn_data.instances_used:
        for instance_sig in fn_data.instances_used:
            if isinstance(instance_sig, str) and fn_data.id:
                Neo4jConnection.execute_query(
                    """
                    MATCH (f:Function {id: $func_id})
                    MATCH (i:Instance {instance_signature: $instance_sig})
                    MERGE (f)-[:USES_INSTANCE_SIGNATURE]->(i)
                    """,
                    parameters={"func_id": fn_data.id, "instance_sig": instance_sig}
                )


def ingest_function_relationships(all_functions: Dict[str, List[Function]]):
    print("Ingesting function relationships (CALLS, DEFINES_WHERE, USES_INSTANCE_SIGNATURE)...")
    rel_count = 0
    for module_name, functions_in_module in all_functions.items():
        for func in functions_in_module:
            _ingest_function_relationships_recursive(func, module_name)
            # Counting relationships is complex here, so just a general message
    print("Function relationships ingestion phase complete.")


def ingest_instance_relationships(all_instances: Dict[str, List[Instance]]):
    print("Ingesting instance relationships (IMPLEMENTS)...")
    count = 0
    for module_name, instances_in_module in all_instances.items():
        for inst in instances_in_module:
            if not inst.id: continue
            for func_in_instance in inst.functions: # These are Function objects
                if func_in_instance.id:
                    Neo4jConnection.execute_query(
                        """
                        MATCH (i:Instance {id: $instance_id})
                        MATCH (f:Function {id: $func_id})
                        MERGE (i)-[:IMPLEMENTS]->(f)
                        """,
                        parameters={"instance_id": inst.id, "func_id": func_in_instance.id},
                    )
                    count +=1
    print(f"Ingested {count} IMPLEMENTS relationships.")

def ingest_field_type_relationships(all_types: Dict[str, List[Type]]):
    print("Ingesting field type relationships (HAS_ATOMIC_TYPE)...")
    count = 0
    for module_name, types_in_module in all_types.items():
        for type_obj in types_in_module:
            if not type_obj.id: continue
            for con_name, fields in type_obj.cons.items():
                constructor_id = f"{type_obj.id}:{con_name}"
                for field in fields:
                    field_id = f"{constructor_id}:{field.field_name}"
                    
                    # Handle HAS_ATOMIC_TYPE
                    if field.field_type.structure.variant == TypeVariant.ATOMIC and \
                       field.field_type.structure.atomic_component:
                        atomic_comp = field.field_type.structure.atomic_component
                        target_type_id = f"{atomic_comp.module_name}:{atomic_comp.type_name}"
                        
                        # Ensure target Type node exists
                        Neo4jConnection.execute_query(
                            "MERGE (t:Type {id: $id}) ON CREATE SET t.name = $name, t.module_name = $module_name",
                            parameters={
                                "id": target_type_id, 
                                "name": atomic_comp.type_name, 
                                "module_name": atomic_comp.module_name
                            }
                        )
                        
                        Neo4jConnection.execute_query(
                            """
                            MATCH (fld:Field {id: $field_id})
                            MATCH (target_type:Type {id: $target_type_id})
                            MERGE (fld)-[:HAS_ATOMIC_TYPE]->(target_type)
                            """,
                            parameters={
                                "field_id": field_id,
                                "target_type_id": target_type_id
                            }
                        )
                        count += 1
                    # TODO: Add handlers for other TypeVariants (LIST, TUPLE, APP, FUNC etc.)
                    # This would involve creating more specific relationships or linking to ComplexType nodes.
                    # For now, their structure is stored as properties on the Field node.
    print(f"Ingested {count} HAS_ATOMIC_TYPE relationships for fields.")

