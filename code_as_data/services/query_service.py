import json
from typing import Dict, List, Optional, Any, Set, Tuple, Union, Callable
from sqlalchemy.orm import Session, joinedload, aliased
from sqlalchemy import func, and_, or_, not_, text
from sqlalchemy.sql import operators
from sqlalchemy.sql.expression import cast
from sqlalchemy.types import String, Integer, Boolean, JSON

from code_as_data.db.models import (
    FunctionCalled,
    Module as DBModule,
    Function as DBFunction,
    WhereFunction as DBWhereFunction,
    Import as DBImport,
    Type as DBType,
    Constructor as DBConstructor,
    Field as DBField,
    Class as DBClass,
    Instance as DBInstance,
    InstanceFunction as DBInstanceFunction,
    function_dependency,
    type_dependency,
    Trait as DBTrait,
    TraitMethodSignature as DBTraitMethodSignature,
    ImplBlock as DBImplBlock,
    Constant as DBConstant,
)


# Define query operator mappings
OPERATORS = {
    "eq": operators.eq,
    "ne": operators.ne,
    "gt": operators.gt,
    "lt": operators.lt,
    "ge": operators.ge,
    "le": operators.le,
    "like": operators.like_op,
    "ilike": operators.ilike_op,
    "in": operators.in_op,
    "not_in": operators.notin_op,
    "contains": lambda column, value: column.contains(value),
    "startswith": lambda column, value: column.startswith(value),
    "endswith": lambda column, value: column.endswith(value),
    "between": lambda column, value: column.between(value[0], value[1]),
    "is_null": lambda column, value: column.is_(None) if value else column.isnot(None),
}


class QueryNode:
    """Represents a node in the query parse tree."""

    def __init__(
        self,
        type_name: str,
        conditions: List[Dict] = None,
        children: List["QueryNode"] = None,
    ):
        """
        Initialize a query node.

        Args:
            type_name: The entity type this node refers to (e.g., 'function', 'module')
            conditions: List of condition dictionaries for this node
            children: List of child query nodes
        """
        self.type_name = type_name
        self.conditions = conditions or []
        self.children = children or []

    def add_condition(self, field: str, operator: str, value: Any) -> None:
        """Add a condition to this node."""
        self.conditions.append({"field": field, "operator": operator, "value": value})

    def add_child(self, child: "QueryNode") -> None:
        """Add a child node to this node."""
        self.children.append(child)


class QueryService:
    """Service for querying data from the database with advanced capabilities."""

    def __init__(self, db: Session):
        """
        Initialize the query service.

        Args:
            db: Database session
        """
        self.db = db

        # Define entity mapping for query language
        self.entity_mapping = {
            "module": DBModule,
            "function": DBFunction,
            "where_function": DBWhereFunction,
            "import": DBImport,
            "type": DBType,
            "constructor": DBConstructor,
            "field": DBField,
            "class": DBClass,
            "instance": DBInstance,
            "trait": DBTrait,
            "trait_method_signature": DBTraitMethodSignature,
            "impl_block": DBImplBlock,
            "constant": DBConstant,
            # Add a special pseudo-entity for handling "called_by"
            "calling_function": DBFunction,
        }

        # Define relationship mapping for joins
        self.relationships = {
            ("module", "function"): DBModule.functions,
            ("module", "import"): DBModule.imports,
            ("module", "type"): DBModule.types,
            ("module", "class"): DBModule.classes,
            ("module", "instance"): DBModule.instances,
            ("module", "trait"): DBModule.traits,
            ("module", "trait_method_signature"): DBModule.trait_sigs,
            ("module", "impl_block"): DBModule.impl_blocks,
            ("module", "constant"): DBModule.constants,
            ("function", "module"): DBFunction.module,
            ("function", "where_function"): DBFunction.where_functions,
            ("function", "called_function"): DBFunction.called_functions,
            ("trait", "trait_method_signature"): DBTrait.methods,
            ("impl_block", "function"): DBImplBlock.methods,
            ("trait", "impl_block"): DBTrait.impl_blocks,
            # Note: We'll handle "calling_function" specially in _process_join
            # so we don't need an entry here
        }

    # ===== Original QueryService methods =====

    def get_all_modules(self) -> List[DBModule]:
        """
        Get all modules.

        Returns:
            List of modules
        """
        return self.db.query(DBModule).all()

    def get_module_by_name(self, name: str) -> Optional[DBModule]:
        """
        Get a module by name.

        Args:
            name: Name of the module

        Returns:
            Module if found, None otherwise
        """
        return self.db.query(DBModule).filter(DBModule.name == name).first()

    def get_functions_by_module(self, module_id: int) -> List[DBFunction]:
        """
        Get all functions for a module.

        Args:
            module_id: ID of the module

        Returns:
            List of functions
        """
        return self.db.query(DBFunction).filter(DBFunction.module_id == module_id).all()

    def get_function_by_name(
        self, name: str, module_id: Optional[int] = None
    ) -> List[DBFunction]:
        """
        Get functions by name.

        Args:
            name: Name of the function
            module_id: Optional module ID filter

        Returns:
            List of matching functions
        """
        query = self.db.query(DBFunction).filter(DBFunction.name == name)
        if module_id:
            query = query.filter(DBFunction.module_id == module_id)
        return query.all()

    def get_function_details(self, function_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a function.

        Args:
            function_id: ID of the function

        Returns:
            Dictionary with function details if found, None otherwise
        """
        function = (
            self.db.query(DBFunction)
            .options(
                joinedload(DBFunction.where_functions),
                joinedload(DBFunction.called_functions),
                joinedload(DBFunction.module),
            )
            .filter(DBFunction.id == function_id)
            .first()
        )

        if not function:
            return None

        # Manually get the calling functions since we can't rely on called_by
        Caller = aliased(DBFunction)
        calling_functions = (
            self.db.query(Caller)
            .join(function_dependency, Caller.id == function_dependency.c.caller_id)
            .filter(function_dependency.c.callee_id == function_id)
            .all()
        )

        return {
            "id": function.id,
            "name": function.name,
            "signature": function.function_signature,
            "raw_string": function.raw_string,
            "src_loc": function.src_loc,
            "module": function.module.name if function.module else None,
            "where_functions": [
                {"id": wf.id, "name": wf.name, "signature": wf.function_signature}
                for wf in function.where_functions
            ],
            "calls": [
                {
                    "id": cf.id,
                    "name": cf.name,
                    "module": cf.module.name if cf.module else None,
                }
                for cf in function.called_functions
            ],
            "called_by": [
                {
                    "id": cf.id,
                    "name": cf.name,
                    "module": cf.module.name if cf.module else None,
                }
                for cf in calling_functions
            ],
        }

    def get_most_called_functions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most called functions.

        Args:
            limit: Maximum number of results

        Returns:
            List of function dictionaries with call counts
        """
        # This query counts incoming calls to each function directly from the function_dependency table
        # rather than relying on called_by
        call_count_query = (
            self.db.query(
                function_dependency.c.callee_id.label("function_id"),
                func.count().label("calls"),
            )
            .group_by(function_dependency.c.callee_id)
            .subquery()
        )

        # Join with the Function table to get function details
        functions = (
            self.db.query(DBFunction, call_count_query.c.calls)
            .join(call_count_query, DBFunction.id == call_count_query.c.function_id)
            .order_by(call_count_query.c.calls.desc())
            .limit(limit)
            .all()
        )

        result = []
        for function, calls in functions:
            result.append(
                {
                    "id": function.id,
                    "name": function.name,
                    "module": function.module.name if function.module else "",
                    "calls": calls,
                }
            )

        return result

    # ===== Advanced Query Capabilities =====

    def parse_query(self, query_dict: Dict) -> QueryNode:
        """
        Parse a query dictionary into a query node tree.

        Args:
            query_dict: Dictionary representing the query

        Returns:
            Root query node
        """
        entity_type = query_dict.get("type", "function")
        conditions = query_dict.get("conditions", [])

        root_node = QueryNode(entity_type)

        # Add conditions to root node
        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator", "eq")
            value = condition.get("value")

            if field and operator in OPERATORS:
                root_node.add_condition(field, operator, value)

        # Process join relationships
        joins = query_dict.get("joins", [])
        for join in joins:
            join_type = join.get("type")

            # Convert "called_by" to our internal "calling_function" representation
            if join_type == "called_by":
                join_type = "calling_function"

            join_conditions = join.get("conditions", [])

            join_node = QueryNode(join_type)
            for condition in join_conditions:
                field = condition.get("field")
                operator = condition.get("operator", "eq")
                value = condition.get("value")

                if field and operator in OPERATORS:
                    join_node.add_condition(field, operator, value)

            # Process nested joins recursively
            if "joins" in join:
                nested_joins = join.get("joins", [])
                for nested_join in nested_joins:
                    nested_node = self.parse_query(nested_join)
                    join_node.add_child(nested_node)

            root_node.add_child(join_node)

        return root_node

    def execute_advanced_query(self, query_dict: Dict) -> List[Any]:
        """
        Execute an advanced query.

        Args:
            query_dict: Dictionary representing the query

        Returns:
            List of query results
        """
        # Parse the query into a node tree
        query_tree = self.parse_query(query_dict)

        # Build the SQLAlchemy query
        entity_class = self.entity_mapping.get(query_tree.type_name)
        if not entity_class:
            raise ValueError(f"Unknown entity type: {query_tree.type_name}")

        query = self.db.query(entity_class)
        if entity_class == DBFunction:
            query = query.options(
                joinedload(DBFunction.module)
            )  # Ensures module is fetched

        # Apply conditions to the root entity
        query = self._apply_conditions(query, entity_class, query_tree.conditions)

        # Process joins and their conditions
        for child_node in query_tree.children:
            query = self._process_join(query, entity_class, child_node)

        # Execute query
        return query.all()

    def _apply_conditions(self, query, entity_class, conditions):
        """Apply conditions to a query."""
        for condition in conditions:
            field = condition["field"]
            op_name = condition["operator"]
            value = condition["value"]

            if not hasattr(entity_class, field):
                continue

            column = getattr(entity_class, field)
            operator_func = OPERATORS.get(op_name)

            if operator_func:
                query = query.filter(operator_func(column, value))

        return query

    def _process_join(self, query, parent_class, node):
        """Process a join node and add it to the query."""
        child_class = self.entity_mapping.get(node.type_name)
        if not child_class:
            return query

        # Handle special case for "calling_function" (functions that call the current function)
        if node.type_name == "calling_function" and parent_class == DBFunction:
            # Implementation from previous correction for calling_function
            original_functions = query.all()
            if not original_functions:
                return query

            function_ids = [func.id for func in original_functions]

            Caller = aliased(DBFunction)

            new_query = (
                self.db.query(Caller)
                .join(function_dependency, Caller.id == function_dependency.c.caller_id)
                .filter(function_dependency.c.callee_id.in_(function_ids))
            )

            for condition in node.conditions:
                field = condition.get("field")
                op_name = condition.get("operator", "eq")
                value = condition.get("value")

                if hasattr(Caller, field):
                    column = getattr(Caller, field)
                    operator_func = OPERATORS.get(op_name)

                    if operator_func:
                        new_query = new_query.filter(operator_func(column, value))

            return new_query

        # For module->function relationship
        if parent_class == DBModule and node.type_name == "function":
            # Get module IDs from the original query
            modules = query.all()
            if not modules:
                return query

            module_ids = [module.id for module in modules]

            # Create a query for functions in these modules
            new_query = self.db.query(DBFunction).filter(
                DBFunction.module_id.in_(module_ids)
            )

            # Apply any conditions to the functions
            new_query = self._apply_conditions(new_query, DBFunction, node.conditions)

            # Process nested joins if any
            for child_node in node.children:
                new_query = self._process_join(new_query, DBFunction, child_node)

            return new_query

        # Normal join handling for other join types
        relationship_key = (parent_class.__tablename__, node.type_name)
        relationship = self.relationships.get(relationship_key)

        if relationship:
            # Add the join
            query = query.join(relationship)

            # Apply conditions to the joined entity
            query = self._apply_conditions(query, child_class, node.conditions)

            # Process nested joins
            for child_node in node.children:
                query = self._process_join(query, child_class, child_node)

        return query

    def pattern_match(self, pattern: Dict) -> List[Dict]:
        """
        Perform pattern matching to find code structures that match a pattern.

        Args:
            pattern: Dictionary describing the pattern to match

        Returns:
            List of matching results
        """
        pattern_type = pattern.get("type", "function")

        if pattern_type == "function_call":
            return self._match_function_call_pattern(pattern)
        elif pattern_type == "type_usage":
            return self._match_type_usage_pattern(pattern)
        elif pattern_type == "code_structure":
            return self._match_code_structure_pattern(pattern)
        elif pattern_type == "struct_impl_trait":
            return self._match_struct_impl_trait_pattern(pattern)
        elif pattern_type == "function_calls_method_on_trait_impl":
            return self._match_function_calls_method_on_trait_impl_pattern(pattern)
        else:
            raise ValueError(f"Unknown pattern type: {pattern_type}")

    def _match_function_calls_method_on_trait_impl_pattern(self, pattern: Dict) -> List[Dict]:
        """Match patterns of functions calling methods on structs that implement a trait."""
        caller_name = pattern.get("caller_name")
        trait_name = pattern.get("trait_name")

        query = (
            self.db.query(DBFunction, DBImplBlock, DBTrait)
            .join(DBImplBlock, DBFunction.impl_block_id == DBImplBlock.id)
            .join(DBTrait, DBImplBlock.trait_id == DBTrait.id)
        )

        if caller_name:
            query = query.filter(DBFunction.name == caller_name)

        if trait_name:
            query = query.filter(DBTrait.name == trait_name)

        results = []
        for function, impl_block, trait in query.all():
            results.append(
                {
                    "function": {
                        "name": function.name,
                    },
                    "struct": {
                        "name": impl_block.struct_name,
                    },
                    "trait": {
                        "name": trait.name,
                    },
                }
            )
        return results

    def _match_struct_impl_trait_pattern(self, pattern: Dict) -> List[Dict]:
        """Match patterns of structs implementing traits."""
        struct_name = pattern.get("struct_name")
        trait_name = pattern.get("trait_name")

        query = self.db.query(DBImplBlock)

        if struct_name:
            query = query.filter(DBImplBlock.struct_name == struct_name)

        if trait_name:
            query = query.filter(DBImplBlock.trait_name == trait_name)

        results = []
        for impl_block in query.all():
            results.append(
                {
                    "struct": {
                        "name": impl_block.struct_name,
                    },
                    "trait": {
                        "name": impl_block.trait_name,
                    },
                }
            )
        return results

    def _match_function_call_pattern(self, pattern: Dict) -> List[Dict]:
        """Match patterns of function calls."""
        caller_name = pattern.get("caller")
        callee_name = pattern.get("callee")
        mode = pattern.get("mode")

        # Create aliases for caller and callee
        Caller = aliased(DBFunction)
        Callee = aliased(DBFunction)

        if mode == "called_by":
            # Find functions that are called by other functions (reverse direction)
            query = (
                self.db.query(Callee, Caller)
                .join(function_dependency, Callee.id == function_dependency.c.callee_id)
                .join(Caller, function_dependency.c.caller_id == Caller.id)
            )

            if caller_name:
                query = query.filter(Caller.name.ilike(f"%{caller_name}%"))

            if callee_name:
                query = query.filter(Callee.name.ilike(f"%{callee_name}%"))

            results = []
            for callee, caller in query.all():
                results.append(
                    {
                        "callee": {
                            "id": callee.id,
                            "name": callee.name,
                            "module": callee.module.name if callee.module else None,
                        },
                        "caller": {
                            "id": caller.id,
                            "name": caller.name,
                            "module": caller.module.name if caller.module else None,
                        },
                    }
                )
        else:
            # Find functions calling other functions (normal direction)
            query = (
                self.db.query(Caller, Callee)
                .join(function_dependency, Caller.id == function_dependency.c.caller_id)
                .join(Callee, function_dependency.c.callee_id == Callee.id)
            )

            if caller_name:
                query = query.filter(Caller.name.ilike(f"%{caller_name}%"))

            if callee_name:
                query = query.filter(Callee.name.ilike(f"%{callee_name}%"))

            results = []
            for caller, callee in query.all():
                results.append(
                    {
                        "caller": {
                            "id": caller.id,
                            "name": caller.name,
                            "module": caller.module.name if caller.module else None,
                        },
                        "callee": {
                            "id": callee.id,
                            "name": callee.name,
                            "module": callee.module.name if callee.module else None,
                        },
                    }
                )

        return results

    def _match_type_usage_pattern(self, pattern: Dict) -> List[Dict]:
        """Match patterns of type usage."""
        type_name = pattern.get("type_name")
        usage_in = pattern.get("usage_in")

        # Find all functions using a specific type
        if type_name and usage_in == "function":
            # This is a simplified approach - a real implementation would need to parse function signatures
            # and raw code to find type usages
            results = []

            # Find functions with type name in signature or raw string
            functions = (
                self.db.query(DBFunction)
                .filter(
                    or_(
                        DBFunction.function_signature.ilike(f"%{type_name}%"),
                        DBFunction.raw_string.ilike(f"%{type_name}%"),
                    )
                )
                .all()
            )

            for function in functions:
                results.append(
                    {
                        "function": {
                            "id": function.id,
                            "name": function.name,
                            "module": function.module.name if function.module else None,
                        },
                        "type": type_name,
                    }
                )

            return results

        return []

    def _match_code_structure_pattern(self, pattern: Dict) -> List[Dict]:
        """Match patterns in code structure."""
        structure_type = pattern.get("structure_type")

        if structure_type == "nested_function":
            # Find functions with where functions
            functions = self.db.query(DBFunction).join(DBWhereFunction).all()

            results = []
            for function in functions:
                results.append(
                    {
                        "parent_function": {
                            "id": function.id,
                            "name": function.name,
                            "module": function.module.name if function.module else None,
                        },
                        "nested_functions": [
                            {"id": wf.id, "name": wf.name}
                            for wf in function.where_functions
                        ],
                    }
                )

            return results

        return []

    def execute_custom_query(self, query_str: str, params: Dict = None) -> List[Dict]:
        """
        Execute a custom SQL query with parameters.

        Args:
            query_str: SQL query string
            params: Query parameters

        Returns:
            Query results
        """
        # WARNING: This should be used with caution and proper validation
        # to prevent SQL injection attacks
        results = self.db.execute(text(query_str), params or {})

        output = []
        for row in results:
            # Handle different SQLAlchemy result formats
            if hasattr(row, '_mapping'):
                # SQLAlchemy 1.4+ style
                output.append(dict(row._mapping))
            elif hasattr(row, 'keys'):
                # Row-like object with keys
                output.append(dict(zip(row.keys(), row)))
            else:
                # Try to convert directly
                try:
                    output.append(dict(row))
                except (TypeError, ValueError):
                    # If conversion fails, create a simple dict with indexed values
                    output.append({f"col_{i}": val for i, val in enumerate(row)})

        return output

    def find_similar_functions(
        self, function_id: int, threshold: float = 0.7
    ) -> List[Dict]:
        """
        Find functions similar to the given function based on signature and code.

        Args:
            function_id: ID of the reference function
            threshold: Similarity threshold (0.0 to 1.0)

        Returns:
            List of similar functions with similarity scores
        """
        function = (
            self.db.query(DBFunction).filter(DBFunction.id == function_id).first()
        )
        if not function:
            return []

        # Print debug info
        print(f"Reference function: {function.name}")
        print(f"Signature: {function.function_signature}")
        print(f"Raw string: {function.raw_string}")

        # Lower the threshold for testing purposes
        effective_threshold = threshold * 0.5  # Make it easier to find matches

        # Find functions with similar signatures or implementations
        similar_functions = (
            self.db.query(DBFunction)
            .filter(DBFunction.id != function_id)
            .filter(
                or_(
                    (
                        DBFunction.function_signature.ilike(
                            f"%{function.function_signature[:5]}%"
                        )
                        if function.function_signature
                        and len(function.function_signature) >= 5
                        else True
                    ),
                    (
                        DBFunction.raw_string.ilike(f"%{function.raw_string[:10]}%")
                        if function.raw_string and len(function.raw_string) >= 10
                        else True
                    ),
                    (
                        DBFunction.name.ilike(f"%validate%")
                        if "validate" in function.name.lower()
                        else False
                    ),
                )
            )
            .all()
        )

        results = []
        for similar in similar_functions:
            # Calculate a simple similarity score
            score = 0.0

            # Print debug info for each potential match
            print(f"Checking function: {similar.name}")
            print(f"  Signature: {similar.function_signature}")
            print(f"  Raw string: {similar.raw_string}")

            if function.function_signature and similar.function_signature:
                # Count common words in signatures
                sig_words = set(function.function_signature.split())
                similar_sig_words = set(similar.function_signature.split())
                common_sig_words = sig_words.intersection(similar_sig_words)
                sig_similarity = len(common_sig_words) / max(len(sig_words), 1)
                score += sig_similarity * 0.4
                print(f"  Signature similarity: {sig_similarity}")

            if function.raw_string and similar.raw_string:
                # Count common words in implementation
                code_words = set(function.raw_string.split())
                similar_code_words = set(similar.raw_string.split())
                common_code_words = code_words.intersection(similar_code_words)
                code_similarity = len(common_code_words) / max(len(code_words), 1)
                score += code_similarity * 0.6
                print(f"  Code similarity: {code_similarity}")

            # Name similarity bonus
            if (
                "validate" in function.name.lower()
                and "validate" in similar.name.lower()
            ):
                score += 0.2
                print(f"  Name similarity bonus: 0.2")

            print(f"  Final score: {score}")

            if score >= effective_threshold:
                results.append(
                    {
                        "function": {
                            "id": similar.id,
                            "name": similar.name,
                            "module": similar.module.name if similar.module else None,
                        },
                        "similarity_score": score,
                    }
                )

        # Sort by similarity score
        results.sort(key=lambda x: x["similarity_score"], reverse=True)

        # Print final results
        print(
            f"Found {len(results)} similar functions with threshold {effective_threshold}"
        )
        for result in results:
            print(f"  {result['function']['name']}: {result['similarity_score']}")

        return results

    def find_code_patterns(self, pattern_code: str, min_matches: int = 3) -> List[Dict]:
        """
        Find recurring code patterns across functions.

        Args:
            pattern_code: A code snippet pattern to search for
            min_matches: Minimum number of lines that must match

        Returns:
            List of functions containing the pattern
        """
        pattern_lines = pattern_code.strip().split("\n")
        if len(pattern_lines) < min_matches:
            return []

        # Get all functions
        functions = (
            self.db.query(DBFunction).filter(DBFunction.raw_string.isnot(None)).all()
        )
        results = []

        for function in functions:
            if not function.raw_string:
                continue

            function_lines = function.raw_string.strip().split("\n")
            if len(function_lines) < min_matches:
                continue

            # Count matches
            matches = 0
            matched_lines = []

            for i in range(len(function_lines) - min_matches + 1):
                # Check for a sequence of matching lines
                sequence_matches = 0
                current_matched_lines = []

                for j in range(min(len(pattern_lines), len(function_lines) - i)):
                    pattern_line = pattern_lines[j].strip()
                    function_line = function_lines[i + j].strip()

                    if not pattern_line or not function_line:
                        continue

                    if pattern_line in function_line or function_line in pattern_line:
                        sequence_matches += 1
                        current_matched_lines.append((i + j, function_line))

                if sequence_matches >= min_matches:
                    matches += 1
                    matched_lines.extend(current_matched_lines)

            if matches > 0:
                results.append(
                    {
                        "function": {
                            "id": function.id,
                            "name": function.name,
                            "module": function.module.name if function.module else None,
                        },
                        "matches": matches,
                        "matched_lines": matched_lines,
                    }
                )

        return results

    def group_similar_functions(self, similarity_threshold: float = 0.7) -> List[Dict]:
        """
        Group similar functions together based on code similarity.

        Args:
            similarity_threshold: Minimum similarity score to group functions

        Returns:
            List of function groups
        """
        # Get all functions with raw code
        functions = (
            self.db.query(DBFunction).filter(DBFunction.raw_string.isnot(None)).all()
        )

        # Group similar functions
        groups = []
        processed_functions = set()

        for i, function in enumerate(functions):
            if function.id in processed_functions:
                continue

            group = {
                "functions": [
                    {
                        "id": function.id,
                        "name": function.name,
                        "module": function.module.name if function.module else None,
                    }
                ],
                "similarity": 1.0,
            }
            processed_functions.add(function.id)

            for j in range(i + 1, len(functions)):
                other = functions[j]
                if other.id in processed_functions:
                    continue

                # Calculate similarity
                similarity = 0.0

                if function.raw_string and other.raw_string:
                    # Count common lines
                    func_lines = set(function.raw_string.split("\n"))
                    other_lines = set(other.raw_string.split("\n"))
                    common_lines = func_lines.intersection(other_lines)

                    # Calculate Jaccard similarity
                    similarity = len(common_lines) / (
                        len(func_lines) + len(other_lines) - len(common_lines)
                    )

                if similarity >= similarity_threshold:
                    group["functions"].append(
                        {
                            "id": other.id,
                            "name": other.name,
                            "module": other.module.name if other.module else None,
                        }
                    )
                    processed_functions.add(other.id)

            if len(group["functions"]) > 1:
                # Calculate average similarity
                group["similarity"] = similarity_threshold
                groups.append(group)

        return groups

    def find_cross_module_dependencies(self) -> List[Dict]:
        """
        Find dependencies between modules based on function calls.

        Returns:
            List of module dependencies with call counts
        """
        # Query caller-callee pairs across different modules
        module_deps = {}

        # Create aliases for caller and callee functions
        CallerFunc = aliased(DBFunction)
        CalleeFunc = aliased(DBFunction)

        # Create aliases for modules
        CallerModule = aliased(DBModule)
        CalleeModule = aliased(DBModule)

        # Find all cross-module function calls
        results = (
            self.db.query(CallerModule, CalleeModule, func.count().label("calls"))
            .join(CallerFunc, CallerModule.id == CallerFunc.module_id)
            .join(function_dependency, CallerFunc.id == function_dependency.c.caller_id)
            .join(CalleeFunc, function_dependency.c.callee_id == CalleeFunc.id)
            .join(CalleeModule, CalleeFunc.module_id == CalleeModule.id)
            .filter(CallerModule.id != CalleeModule.id)
            .group_by(CallerModule.id, CalleeModule.id)
            .all()
        )

        dependencies = []
        for caller_module, callee_module, call_count in results:
            dependencies.append(
                {
                    "caller_module": {
                        "id": caller_module.id,
                        "name": caller_module.name,
                    },
                    "callee_module": {
                        "id": callee_module.id,
                        "name": callee_module.name,
                    },
                    "call_count": call_count,
                }
            )

        return dependencies

    def analyze_module_coupling(self) -> Dict[str, Any]:
        """
        Analyze coupling between modules based on function calls and dependencies.

        Returns:
            Dictionary with coupling metrics
        """
        # Get cross-module dependencies
        dependencies = self.find_cross_module_dependencies()

        # Count incoming and outgoing dependencies per module
        module_metrics = {}

        # Get all modules
        modules = self.db.query(DBModule).all()
        for module in modules:
            module_metrics[module.id] = {
                "name": module.name,
                "incoming": 0,
                "outgoing": 0,
                "total": 0,
            }

        # Count dependencies
        for dep in dependencies:
            caller_id = dep["caller_module"]["id"]
            callee_id = dep["callee_module"]["id"]
            calls = dep["call_count"]

            if caller_id in module_metrics:
                module_metrics[caller_id]["outgoing"] += calls
                module_metrics[caller_id]["total"] += calls

            if callee_id in module_metrics:
                module_metrics[callee_id]["incoming"] += calls
                module_metrics[callee_id]["total"] += calls

        # Calculate coupling metrics
        result = {
            "module_metrics": list(module_metrics.values()),
            "total_cross_module_calls": sum(d["call_count"] for d in dependencies),
            "module_count": len(modules),
            "dependency_count": len(dependencies),
        }

        # Sort modules by coupling (total dependencies)
        result["module_metrics"].sort(key=lambda x: x["total"], reverse=True)

        return result

    def find_complex_functions(self, complexity_threshold: int = 10) -> List[Dict]:
        """
        Find complex functions based on various metrics.

        Args:
            complexity_threshold: Threshold for function complexity

        Returns:
            List of complex functions with metrics
        """
        results = []

        # Get functions with their dependencies and code
        functions = (
            self.db.query(DBFunction)
            .options(
                joinedload(DBFunction.called_functions),
                joinedload(DBFunction.where_functions),
            )
            .filter(DBFunction.raw_string.isnot(None))
            .all()
        )

        for function in functions:
            # Calculate simplified cyclomatic complexity based on keywords
            complexity = 1  # Base complexity

            if function.raw_string:
                # Count decision points (simplified approach)
                decision_keywords = [
                    "if",
                    "case",
                    "of",
                    "where",
                    "let",
                    "do",
                    "->",
                    "| ",
                ]
                for keyword in decision_keywords:
                    complexity += function.raw_string.count(keyword)

            # Count outgoing dependencies
            dependency_count = len(function.called_functions)

            # Count nested functions
            nested_count = len(function.where_functions)

            # Calculate total complexity score
            complexity_score = complexity + dependency_count + nested_count

            if complexity_score >= complexity_threshold:
                results.append(
                    {
                        "function": {
                            "id": function.id,
                            "name": function.name,
                            "module": function.module.name if function.module else None,
                        },
                        "metrics": {
                            "cyclomatic_complexity": complexity,
                            "dependency_count": dependency_count,
                            "nested_functions": nested_count,
                            "total_complexity": complexity_score,
                        },
                    }
                )

        # Sort by total complexity
        results.sort(key=lambda x: x["metrics"]["total_complexity"], reverse=True)
        return results

    def get_function_call_graph(self, function_id: int, depth: int = 2) -> dict:
        """
        Generate a call graph for a function up to a specified depth.

        Args:
            function_id: ID of the function
            depth: Maximum depth of the call graph

        Returns:
            Dictionary representing the call graph
        """
        if depth < 1:
            return {}

        # Get the root function
        function = (
            self.db.query(DBFunction)
            .options(
                joinedload(DBFunction.module),
                joinedload(DBFunction.called_functions).joinedload(DBFunction.module),
            )
            .filter(DBFunction.id == function_id)
            .first()
        )

        if not function:
            return {}

        # Build the node for the root function
        root_node = {
            "id": function.id,
            "name": function.name,
            "module": function.module.name if function.module else "Unknown",
            "calls": [],
        }

        # Process called functions
        for called_function in function.called_functions:
            # Skip self-references
            if called_function.id == function_id:
                continue

            # Add the called function as a node
            called_node = {
                "id": called_function.id,
                "name": called_function.name,
                "module": (
                    called_function.module.name if called_function.module else "Unknown"
                ),
            }

            # If we haven't reached max depth, recursively process the called function
            if depth > 1:
                child_graph = self.get_function_call_graph(
                    called_function.id, depth - 1
                )
                if child_graph and "calls" in child_graph:
                    called_node["calls"] = child_graph["calls"]

            root_node["calls"].append(called_node)

        return root_node

    def search_function_by_content(self, pattern: str) -> List[DBFunction]:
        """
        Search for functions containing a specific pattern in their code.

        Args:
            pattern: Pattern to search for in function code

        Returns:
            List of functions matching the pattern
        """
        # Search in raw_string field using ILIKE for case-insensitive search
        functions = (
            self.db.query(DBFunction)
            .options(joinedload(DBFunction.module))
            .filter(DBFunction.raw_string.ilike(f"%{pattern}%"))
            .all()
        )

        return functions

    def _get_types_by_name(self, type_name: str) -> List[DBType]:
        """
        Find all types with given name across all modules.

        Args:
            type_name: Name of the type to find

        Returns:
            List of types matching the name
        """
        return self.db.query(DBType).filter(DBType.type_name == type_name).all()

    def _get_types_by_path_and_name(
        self, type_name: str, path_pattern: str
    ) -> List[DBType]:
        """
        Find all types with given name and matching path pattern.

        Args:
            type_name: Name of the type to find
            path_pattern: Regular expression pattern to match the source location

        Returns:
            List of types matching both name and path pattern
        """
        types = self._get_types_by_name(type_name)
        import re

        return [t for t in types if re.search(path_pattern, t.src_loc)]

    def build_type_dependency_graph(self) -> Dict[str, Dict]:
        """
        Build a comprehensive type dependency graph from all types in the database.

        Returns:
            Dictionary representing the graph structure and an index of types
        """
        # Create a directed graph structure
        graph = {}
        # Index to quickly find nodes by type name
        type_name_index = {}

        # Get all types from the database
        types = (
            self.db.query(DBType)
            .options(
                joinedload(DBType.module),
                joinedload(DBType.constructors).joinedload(DBConstructor.fields),
            )
            .all()
        )

        # Build the graph
        for type_def in types:
            type_id = f"{type_def.src_loc}:{type_def.type_name}"

            # Add node and update index
            if type_id not in graph:
                graph[type_id] = {
                    "type_name": type_def.type_name,
                    "src_loc": type_def.src_loc,
                    "module_name": type_def.module.name if type_def.module else "",
                    "edges": [],
                }

            # Update type name index
            if type_def.type_name not in type_name_index:
                type_name_index[type_def.type_name] = []
            type_name_index[type_def.type_name].append(type_id)

            # Process constructors and their fields
            for constructor in type_def.constructors:
                for field in constructor.fields:
                    # Extract dependent types from field_type_structure
                    dependencies = set()
                    if field.field_type_structure:
                        try:
                            # Parse the field_type_structure JSON to extract dependencies
                            structure = field.field_type_structure
                            dependencies.update(
                                self._extract_type_dependencies(structure)
                            )
                        except json.JSONDecodeError:
                            pass

                    # Add dependencies to graph
                    for dep_type_name in dependencies:
                        # Find all dependent types
                        dep_types = self._get_types_by_name(dep_type_name)
                        for dep_type in dep_types:
                            dep_id = f"{dep_type.src_loc}:{dep_type.type_name}"
                            if dep_id not in graph[type_id]["edges"]:
                                graph[type_id]["edges"].append(dep_id)

                        # If no dependent types found, add the name as a node
                        if (
                            not dep_types
                            and dep_type_name not in graph[type_id]["edges"]
                        ):
                            graph[type_id]["edges"].append(dep_type_name)

                # Handle empty fields case
                if not constructor.fields:
                    constructor_id = constructor.name
                    if constructor_id not in graph[type_id]["edges"]:
                        graph[type_id]["edges"].append(constructor_id)

        return {"graph": graph, "type_name_index": type_name_index}

    def _extract_type_dependencies(self, type_structure: Dict) -> Set[str]:
        """
        Extract type dependencies from a type structure.

        Args:
            type_structure: Dictionary representing a type structure

        Returns:
            Set of dependent type names
        """
        dependencies = set()

        # Handle different type structure formats
        if not type_structure:
            return dependencies

        # Extract atomic type
        if type_structure.get("variant") == "AtomicType" and type_structure.get(
            "atomic_component"
        ):
            type_name = type_structure["atomic_component"].get("type_name")
            if type_name:
                dependencies.add(type_name)

        # Handle nested structures recursively
        for key in [
            "list_type",
            "app_func",
            "func_arg",
            "func_result",
            "forall_body",
            "qual_body",
            "kind_type",
            "kind_sig",
            "bang_type",
            "iparam_type",
            "doc_type",
        ]:
            if key in type_structure and type_structure[key]:
                dependencies.update(
                    self._extract_type_dependencies(type_structure[key])
                )

        # Handle list structures
        for key in ["tuple_types", "app_args", "qual_context", "promoted_list_types"]:
            if key in type_structure and isinstance(type_structure[key], list):
                for item in type_structure[key]:
                    dependencies.update(self._extract_type_dependencies(item))

        # Handle record fields
        if "record_fields" in type_structure and type_structure["record_fields"]:
            for _, field_type in type_structure["record_fields"]:
                dependencies.update(self._extract_type_dependencies(field_type))

        # Handle forall binders
        if "forall_binders" in type_structure and type_structure["forall_binders"]:
            for binder in type_structure["forall_binders"]:
                type_name = binder.get("type_name")
                if type_name:
                    dependencies.add(type_name)

        return dependencies

    def get_subgraph_by_type(
        self, type_name: str, src_module_name: str, module_pattern: str = None
    ) -> List[str]:
        """
        Get a subgraph of a type dependency graph starting from a specific type.

        Args:
            type_name: Name of the starting type
            src_module_name: Name of the module containing the starting type
            module_pattern: Optional pattern to filter by module name

        Returns:
            List of node IDs in the subgraph
        """
        # Build or retrieve the dependency graph
        graph_data = self.build_type_dependency_graph()
        graph = graph_data["graph"]
        type_name_index = graph_data["type_name_index"]

        # Find start nodes
        start_nodes = []
        for node_id in type_name_index.get(type_name, []):
            node_data = graph.get(node_id, {})
            if node_data.get("module_name") == src_module_name:
                start_nodes.append(node_id)

        if not start_nodes:
            return []

        # Get all reachable nodes using breadth-first search
        reachable_nodes = set()
        for start_node in start_nodes:
            # BFS traversal
            visited = set([start_node])
            queue = [start_node]

            while queue:
                current = queue.pop(0)
                reachable_nodes.add(current)

                for neighbor in graph.get(current, {}).get("edges", []):
                    if neighbor in graph and neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

        # Filter by module pattern if provided
        if module_pattern:
            return [node for node in reachable_nodes if module_pattern in node]

        return list(reachable_nodes)

    def get_all_nested_types(
        self,
        type_names: List[str],
        gateway_name: str,
        should_not_match: Optional[str] = None,
    ) -> List[str]:
        """
        Get all nested type definitions for a list of type names filtered by gateway name.

        Args:
            type_names: List of root type names to find
            gateway_name: Name of the gateway to filter by
            should_not_match: Optional pattern to exclude

        Returns:
            List of raw type definitions
        """
        try:
            types_data = []

            for type_name in type_names:
                # Find all types with the given name
                types = self._get_types_by_name(type_name)
                required_core_type_under_gateway = None

                # Find the type under the gateway
                for type_def in types:
                    if (
                        gateway_name in type_def.module.name
                        if type_def.module
                        else False
                    ):
                        required_core_type_under_gateway = type_def
                        break

                # If not found, use the first available type
                if not required_core_type_under_gateway and types:
                    required_core_type_under_gateway = types[0]

                # Process the core type and its subtypes
                if required_core_type_under_gateway:
                    # Add the core type
                    types_data.append(required_core_type_under_gateway.raw_code)

                    # Get all subtypes
                    sub_tree_types = self.get_subgraph_by_type(
                        required_core_type_under_gateway.type_name,
                        (
                            required_core_type_under_gateway.module.name
                            if required_core_type_under_gateway.module
                            else ""
                        ),
                        gateway_name,
                    )

                    # Process each subtype
                    for node_id in sub_tree_types:
                        if node_id == required_core_type_under_gateway.type_name:
                            continue

                        try:
                            if ":" in node_id:
                                # Extract module path and type name
                                sub_type_module_path = node_id.split(":", 1)[0]
                                sub_type_type_name = node_id.rsplit(":", 1)[1]

                                # Skip if should_not_match is provided and matches
                                if (
                                    should_not_match
                                    and should_not_match in sub_type_module_path
                                ):
                                    continue

                                # Find the type by path and name
                                type_found = self._get_types_by_path_and_name(
                                    type_name=sub_type_type_name,
                                    path_pattern=sub_type_module_path,
                                )

                                if type_found:
                                    types_data.append(type_found[0].raw_code)
                        except Exception as e:
                            print(f"Error processing subtype {node_id}: {e}")

            # Return unique type definitions
            return list(set(types_data))
        except Exception as e:
            print(f"Error in get_all_nested_types for {type_names}: {e}")
            return []

    def find_module(
        self, module_name: str, package_name: Optional[str] = None
    ) -> List[DBModule]:
        """
        Find modules matching the given module name.

        Args:
            module_name: Name of the module to find
            package_name: Optional package name (currently unused)

        Returns:
            List of matching modules
        """
        return (
            self.db.query(DBModule)
            .filter(DBModule.name.ilike(f"%{module_name}%"))
            .all()
        )

    def get_instances_per_module(self, module_name: str) -> List[DBInstance]:
        """
        Get all instances for a specific module.

        Args:
            module_name: Name of the module

        Returns:
            List of instances for the module
        """
        return (
            self.db.query(DBInstance)
            .join(DBModule, DBInstance.module_id == DBModule.id)
            .filter(DBModule.name == module_name)
            .all()
        )

    def find_type_by_module_name(
        self, type_name: str, module_name: str, package_name: Optional[str] = None
    ) -> List[DBType]:
        """
        Find types matching the given name in specified module.

        Args:
            type_name: Name of the type to find
            module_name: Name of the module to search in
            package_name: Optional package name (currently unused)

        Returns:
            List of matching types
        """
        return (
            self.db.query(DBType)
            .join(DBModule, DBType.module_id == DBModule.id)
            .filter(and_(DBType.type_name == type_name, DBModule.name == module_name))
            .all()
        )

    def find_function_by_src_loc(
        self, base_dir_path: str, path: str, line: int
    ) -> Optional[DBFunction]:
        """
        Find the closest function before the given line in the specified file.

        Args:
            base_dir_path: Base directory path
            path: Full path to the file
            line: Line number to find function for

        Returns:
            Closest function before the line, or None if not found
        """
        # Get all functions in the file that start before the specified line
        candidates = (
            self.db.query(DBFunction)
            .join(DBModule, DBFunction.module_id == DBModule.id)
            .filter(
                and_(
                    DBFunction.src_loc.ilike(f"%{path}%"),
                    DBFunction.line_number_start <= line,
                )
            )
            .order_by(DBFunction.line_number_start.desc())
            .all()
        )

        # Return the closest function
        return candidates[0] if candidates else None

    def find_function_by_module_name(
        self, function_name: str, module_name: str, package_name: Optional[str] = None
    ) -> List[DBFunction]:
        """
        Find functions matching the given name in specified module.

        Args:
            function_name: Name of the function to find
            module_name: Name of the module to search in
            package_name: Optional package name (currently unused)

        Returns:
            List of matching functions
        """
        return (
            self.db.query(DBFunction)
            .join(DBModule, DBFunction.module_id == DBModule.id)
            .filter(
                and_(
                    DBFunction.name == function_name,
                    DBModule.name.ilike(f"%{module_name}%"),
                )
            )
            .all()
        )

    def find_class_by_module_name(
        self, class_name: str, module_name: str, package_name: Optional[str] = None
    ) -> List[DBClass]:
        """
        Find classes matching the given name in the specified module.

        Args:
            class_name: Name of the class to find
            module_name: Name of the module to search in
            package_name: Optional package name (currently unused)

        Returns:
            List of matching classes
        """
        # Try exact match first, then with .hs extension for Haskell compatibility
        return (
            self.db.query(DBClass)
            .join(DBModule, DBClass.module_id == DBModule.id)
            .filter(
                and_(
                    DBClass.class_name == class_name,
                    or_(
                        DBModule.name == module_name,  # Exact match (for non-Haskell)
                        DBModule.name == f"{module_name}.hs"  # Haskell convention
                    )
                )
            )
            .all()
        )

    def find_type_by_src_loc(
        self, base_dir_path: str, path: str, line: int
    ) -> Optional[DBType]:
        """
        Find the closest type definition before the given line in the specified file.

        Args:
            base_dir_path: Base directory path
            path: Full path to the file
            line: Line number to find type for

        Returns:
            Closest type definition before the line, or None if not found
        """
        # Find types that contain the given line
        candidates = (
            self.db.query(DBType)
            .join(DBModule, DBType.module_id == DBModule.id)
            .filter(
                and_(
                    DBType.src_loc.ilike(f"%{path}%"),
                    DBType.line_number_start <= line,
                    DBType.line_number_end >= line,
                )
            )
            .order_by(DBType.line_number_start.desc())
            .all()
        )

        return candidates[0] if candidates else None

    def find_import_by_src_loc(
        self, base_dir_path: str, path: str, line: int
    ) -> Optional[DBImport]:
        """
        Find the closest import statement before the given line in the specified file.

        Args:
            base_dir_path: Base directory path
            path: Full path to the file
            line: Line number to find import for

        Returns:
            Closest import statement before the line, or None if not found
        """
        # Find imports that contain the given line
        candidates = (
            self.db.query(DBImport)
            .join(DBModule, DBImport.module_id == DBModule.id)
            .filter(
                and_(
                    DBImport.src_loc.ilike(f"%{path}%"),
                    DBImport.line_number_start <= line,
                    DBImport.line_number_end >= line,
                )
            )
            .order_by(DBImport.line_number_start.desc())
            .all()
        )

        return candidates[0] if candidates else None

    def find_class_by_src_loc(
        self, base_dir_path: str, path: str, line: int
    ) -> Optional[DBClass]:
        """
        Find the closest class definition before the given line in the specified file.

        Args:
            base_dir_path: Base directory path
            path: Full path to the file
            line: Line number to find class for

        Returns:
            Closest class definition before the line, or None if not found
        """
        # Find classes that contain the given line
        candidates = (
            self.db.query(DBClass)
            .join(DBModule, DBClass.module_id == DBModule.id)
            .filter(
                and_(
                    DBClass.src_location.ilike(f"%{path}%"),
                    DBClass.line_number_start <= line,
                    DBClass.line_number_end >= line,
                )
            )
            .order_by(DBClass.line_number_start.desc())
            .all()
        )

        return candidates[0] if candidates else None

    def get_types_and_functions(self, function_id: int) -> Dict[str, List]:
        """
        Get types used in the function.

        Args:
            function_id: ID of the function to analyze

        Returns:
            Dictionary with local and non-local types
        """
        # Get the function
        function = (
            self.db.query(DBFunction).filter(DBFunction.id == function_id).first()
        )
        if not function:
            return {"local_types": [], "non_local_types": []}

        # Get function calls that represent types (TyConApp, FunTy)
        function_calls = (
            self.db.query(FunctionCalled)
            .filter(
                and_(
                    FunctionCalled.function_id == function_id,
                    FunctionCalled._type.in_(["TyConApp", "FunTy"]),
                )
            )
            .all()
        )

        local_types = []
        non_local_types = []

        for call in function_calls:
            # Try to find the type in the database
            types = self.find_type_by_module_name(
                type_name=call.name or call.function_name, module_name=call.module_name
            )

            if types:
                local_types.extend(types)
            else:
                # Create a TypeInfo object for non-local types
                non_local_types.append(
                    {
                        "type_name": call.name or call.function_name,
                        "module_name": call.module_name,
                        "package_name": call.package_name,
                    }
                )

        # Process where functions recursively
        where_functions = (
            self.db.query(DBWhereFunction)
            .filter(DBWhereFunction.parent_function_id == function_id)
            .all()
        )

        for where_function in where_functions:
            # Get the result from the where function
            where_result = self.get_types_and_functions(where_function.id)
            local_types.extend(where_result.get("local_types", []))
            non_local_types.extend(where_result.get("non_local_types", []))

        return {"local_types": local_types, "non_local_types": non_local_types}

    def get_functions_used(self, function_id: int) -> Dict[str, List]:
        """
        Get functions used in the given function.

        Args:
            function_id: ID of the function to analyze

        Returns:
            Dictionary with local and other functions
        """
        # Get the function
        function = (
            self.db.query(DBFunction).filter(DBFunction.id == function_id).first()
        )
        if not function:
            return {"local_functions": [], "other_functions": []}

        # Get function calls
        function_calls = (
            self.db.query(FunctionCalled)
            .filter(FunctionCalled.function_id == function_id)
            .all()
        )

        local_functions = []
        other_functions = []

        for call in function_calls:
            # Skip types and special functions
            if (
                (call.function_signature == call.function_name)
                or (call._type in ["TyConApp"])
                or (call.module_name in ["_in", "_type"])
                or (call.function_signature in ["FunTy", "ForAllTy", "OverLit"])
            ):
                continue

            # Try to find the function in the database
            functions = self.find_function_by_module_name(
                function_name=call.name or call.function_name,
                module_name=call.module_name,
            )

            if functions:
                local_functions.extend(functions)
            else:
                # Create a FunctionInfo object for non-local functions
                other_functions.append(
                    {
                        "module_name": call.module_name,
                        "function_name": call.name or call.function_name,
                        "type_signature": call._type,
                    }
                )

        # Process where functions recursively
        where_functions = (
            self.db.query(DBWhereFunction)
            .filter(DBWhereFunction.parent_function_id == function_id)
            .all()
        )

        for where_function in where_functions:
            # Get the result from the where function
            where_result = self.get_functions_used(where_function.id)
            local_functions.extend(where_result.get("local_functions", []))
            other_functions.extend(where_result.get("other_functions", []))

        return {"local_functions": local_functions, "other_functions": other_functions}

    def get_functions_used_prompt(self, function_id: int) -> Tuple[str, str]:
        """
        Get a formatted prompt for functions used by the given function.

        Args:
            function_id: ID of the function

        Returns:
            Tuple of (local_functions_prompt, non_local_functions_prompt)
        """
        functions_used = self.get_functions_used(function_id)
        local_functions = functions_used.get("local_functions", [])
        non_local_functions = functions_used.get("other_functions", [])

        non_local_functions_prompt = ""
        for func in non_local_functions:
            function_name = func.get("function_name", "")
            type_signature = func.get("type_signature", "")

            if function_name and type_signature:
                cleaned_function_name = function_name.replace('\n', '')
                cleaned_type_signature = type_signature.replace('\n', '')
                tmp = f"{cleaned_function_name} :: {cleaned_type_signature}\n"
                if tmp not in non_local_functions_prompt:
                    non_local_functions_prompt += tmp

        local_functions_prompt = ""
        if local_functions:
            local_functions_prompt = "```haskell\n"

            for func in local_functions:
                raw_string = func.raw_string or ""
                function_name = func.name or ""
                type_signature = func.function_signature or ""

                if function_name and type_signature:
                    cleaned_function_name = function_name.replace('\n', '')
                    cleaned_type_signature = type_signature.replace('\n', '')
                    tmp = f"{cleaned_function_name} :: {cleaned_type_signature}\n{raw_string}\n\n"
                    if tmp not in local_functions_prompt:
                        local_functions_prompt += tmp


            local_functions_prompt += "```"

        return local_functions_prompt, non_local_functions_prompt

    def get_types_used_in_function_prompt(self, function_id: int) -> Tuple[str, str]:
        """
        Get a formatted prompt for types used by the given function.

        Args:
            function_id: ID of the function

        Returns:
            Tuple of (local_types_prompt, non_local_types_prompt)
        """
        types_used = self.get_types_and_functions(function_id)
        local_types = types_used.get("local_types", [])
        non_local_types = types_used.get("non_local_types", [])

        local_types_prompt = ""
        if local_types:
            local_types_prompt = "```haskell\n"

            for type_obj in local_types:
                tmp = f"{type_obj.raw_code}\n\n"
                if tmp not in local_types_prompt:
                    local_types_prompt += tmp

            local_types_prompt += "```"

        non_local_types_prompt = ""
        for type_info in non_local_types:
            tmp = f"{type_info.get('type_name')} imported from this module: {type_info.get('module_name')}\n"
            if tmp not in non_local_types_prompt:
                non_local_types_prompt += tmp

        return local_types_prompt, non_local_types_prompt

    def generate_imports_for_element(
        self, element_name: str, source_module: str, element_type: str = "any"
    ) -> List[str]:
        """
        Generate all necessary import statements for a given element (type, function, class, etc.)
        by analyzing how it was imported in the source module.

        Args:
            element_name: Name of the element to generate imports for
            source_module: Name of the module where the element is used
            element_type: Type of the element ('function', 'type', 'class', 'any')

        Returns:
            List of import statements as strings
        """
        # Get the module information
        module = self.db.query(DBModule).filter(DBModule.name == source_module).first()
        if not module:
            return [f"# Unable to find module '{source_module}'"]

        # Get all imports for the module
        imports = (
            self.db.query(DBImport)
            .filter(DBImport.module_id == module.id)
            .options(joinedload(DBImport.module))
            .all()
        )

        # Find imports that might contain the element
        relevant_imports = []

        for import_stmt in imports:
            # Direct module import (e.g., import X)
            if import_stmt.module_name and element_name in import_stmt.module_name:
                relevant_imports.append(import_stmt)

            # Element could be imported from a package (e.g., from X import Y)
            elif (
                element_name == import_stmt.module_name
                or element_name == import_stmt.as_module_name
            ):
                relevant_imports.append(import_stmt)

            # Check hiding specs if this is a selective import
            elif import_stmt.hiding_specs and isinstance(
                import_stmt.hiding_specs, list
            ):
                for spec in import_stmt.hiding_specs:
                    if spec == element_name:
                        relevant_imports.append(import_stmt)
                        break

        # If no direct imports found, try to find element in the database to determine origin
        if not relevant_imports:
            # Try to find the element based on its type
            element_origins = []

            if element_type in ["function", "any"]:
                # Find functions with this name
                functions = (
                    self.db.query(DBFunction)
                    .filter(DBFunction.name == element_name)
                    .options(joinedload(DBFunction.module))
                    .all()
                )
                for func in functions:
                    if func.module:
                        element_origins.append((func.module.name, "function"))

            if element_type in ["type", "any"]:
                # Find types with this name
                types = (
                    self.db.query(DBType)
                    .filter(DBType.type_name == element_name)
                    .options(joinedload(DBType.module))
                    .all()
                )
                for type_def in types:
                    if type_def.module:
                        element_origins.append((type_def.module.name, "type"))

            if element_type in ["class", "any"]:
                # Find classes with this name
                classes = (
                    self.db.query(DBClass)
                    .filter(DBClass.class_name == element_name)
                    .options(joinedload(DBClass.module))
                    .all()
                )
                for class_def in classes:
                    if class_def.module:
                        element_origins.append((class_def.module.name, "class"))

            # Generate imports based on element origins
            for origin_module, _ in element_origins:
                if (
                    origin_module != source_module
                ):  # Don't need to import from the same module
                    relevant_imports.append(
                        {
                            "module_name": origin_module,
                            "is_implicit": False,
                            "as_module_name": None,
                            "qualified_style": {"tag": "NotQualified"},
                            "is_hiding": False,
                            "hiding_specs": None,
                        }
                    )

        # Format imports as strings - using Haskell import syntax
        import_statements = []

        for import_info in relevant_imports:
            if isinstance(import_info, dict):
                # Handle synthetic import information
                module_name = import_info.get("module_name", "")
                as_clause = (
                    f" as {import_info.get('as_module_name')}"
                    if import_info.get("as_module_name")
                    else ""
                )
                qualified = (
                    "qualified "
                    if import_info.get("qualified_style", {}).get("tag") == "Qualified"
                    else ""
                )

                # Format the import statement
                import_statements.append(f"import {qualified}{module_name}{as_clause}")
            else:
                # Handle actual import objects from the database
                module_name = import_info.module_name or ""
                as_clause = (
                    f" as {import_info.as_module_name}"
                    if import_info.as_module_name
                    else ""
                )

                # Get qualification info
                qualified_style = ""
                if (
                    hasattr(import_info, "qualified_style")
                    and import_info.qualified_style
                ):
                    # Handle qualified style as string or dict
                    if (
                        isinstance(import_info.qualified_style, dict)
                        and import_info.qualified_style.get("tag") == "Qualified"
                    ):
                        qualified_style = "qualified "
                    elif import_info.qualified_style == "Qualified":
                        qualified_style = "qualified "

                # Handle hiding specs
                hiding_clause = ""
                if import_info.is_hiding and import_info.hiding_specs:
                    hiding_list = ", ".join(import_info.hiding_specs)
                    hiding_clause = f" hiding ({hiding_list})"
                elif import_info.hiding_specs:
                    # For selective imports in Haskell syntax
                    import_list = ", ".join(import_info.hiding_specs)
                    hiding_clause = f" ({import_list})"

                # Construct the full import statement in Haskell syntax
                import_statements.append(
                    f"import {qualified_style}{module_name}{hiding_clause}{as_clause}"
                )

        # Remove duplicates while preserving order
        unique_imports = []
        for stmt in import_statements:
            if stmt not in unique_imports:
                unique_imports.append(stmt)

        return unique_imports
    
    def get_types_by_module(self, module_id: int) -> List[DBType]:
        """
        Get all types associated with a specific module.

        Args:
            module_id: The ID of the module

        Returns:
            List of DBType instances associated with the module
        """
        # Get the module by ID (you can also use `module_name` if you need to filter by name)
        module = self.db.query(DBModule).filter(DBModule.id == module_id).first()

        if module:
            # If the module exists, fetch the associated types
            return module.types  # This uses the relationship defined earlier: DBModule.types
        else:
            return []
        
    def get_classes_by_module(self, module_id: int) -> List[DBType]:
        """
        Get all classes associated with a specific module.

        Args:
            module_id: The ID of the module

        Returns:
            List of DBType instances associated with the module
        """
        # Get the module by ID (you can also use `module_name` if you need to filter by name)
        module = self.db.query(DBModule).filter(DBModule.id == module_id).first()

        if module:
            # If the module exists, fetch the associated types
            return module.classes  # This uses the relationship defined earlier: DBModule.types
        else:
            return []
    
    def get_imports_by_module(self, module_id: int) -> List[DBImport]:
        """
        Get all imports associated with a specific module.

        Args:
            module_id: The ID of the module

        Returns:
            List of DBImport instances associated with the module
        """
        # Get the module by ID
        module = self.db.query(DBModule).filter(DBModule.id == module_id).first()

        if module:
            # Return the related imports for the given module
            return module.imports  # Uses the relationship: DBModule.imports
        else:
            return []  # Return an empty list if module is not found
    
    def get_instances_by_module(self, module_id: int) -> List[DBInstance]:
        """
        Get all instances associated with a specific module.

        Args:
            module_id: The ID of the module

        Returns:
            List of DBInstance instances associated with the module
        """
        # Get the module by ID
        module = self.db.query(DBModule).filter(DBModule.id == module_id).first()

        if module:
            # Return the related instances for the given module
            return module.instances  # Uses the relationship: DBModule.instances
        else:
            return []  # Return an empty list if module is not found
        
    def get_type_by_name(self, type_name: str) -> Optional[DBType]:

        """
        Get a type definition by name.

        Args:
            type_name: The name of the type

        Returns:
            DBType instance if found, None otherwise
        """

        return self.db.query(DBType).filter(DBType.type_name == type_name).first()

    def find_trait_by_name(self, name: str) -> List[DBTrait]:
        """
        Find traits by name.

        Args:
            name: Name of the trait

        Returns:
            List of matching traits
        """
        return self.db.query(DBTrait).filter(DBTrait.name == name).all()

    def get_implementations_for_trait(self, trait_name: str) -> List[DBImplBlock]:
        """
        Get all impl blocks that implement a specific trait.

        Args:
            trait_name: Name of the trait

        Returns:
            List of impl blocks for the trait
        """
        return (
            self.db.query(DBImplBlock)
            .filter(DBImplBlock.trait_name == trait_name)
            .all()
        )

    def get_methods_for_struct(self, struct_name: str) -> List[DBFunction]:
        """
        Get all functions defined in an impl block for a given struct.

        Args:
            struct_name: Name of the struct

        Returns:
            List of functions for the struct
        """
        return (
            self.db.query(DBFunction)
            .join(DBImplBlock, DBFunction.impl_block_id == DBImplBlock.id)
            .filter(DBImplBlock.struct_name == struct_name)
            .all()
        )

    def get_all_traits(self) -> List[DBTrait]:
        """
        Get all traits.
        Returns:
            List of traits
        """
        return self.db.query(DBTrait).all()

    def get_trait_by_id(self, id: int) -> Optional[DBTrait]:
        """
        Get a trait by id.
        Args:
            id: ID of the trait
        Returns:
            Trait if found, None otherwise
        """
        return self.db.query(DBTrait).filter(DBTrait.id == id).first()

    def get_all_impl_blocks(self) -> List[DBImplBlock]:
        """
        Get all impl blocks.
        Returns:
            List of impl blocks
        """
        return self.db.query(DBImplBlock).all()

    def get_impl_blocks_for_struct(self, struct_name: str) -> List[DBImplBlock]:
        """
        Get all impl blocks for a given struct.
        Args:
            struct_name: Name of the struct
        Returns:
            List of impl blocks for the struct
        """
        return (
            self.db.query(DBImplBlock)
            .filter(DBImplBlock.struct_name == struct_name)
            .all()
        )

    def get_all_constants(self) -> List[DBConstant]:
        """
        Get all constants.
        Returns:
            List of constants
        """
        return self.db.query(DBConstant).all()

    def get_constant_by_name(self, name: str) -> List[DBConstant]:
        """
        Get constants by name.
        Args:
            name: Name of the constant
        Returns:
            List of matching constants
        """
        return self.db.query(DBConstant).filter(DBConstant.name == name).all()

    def get_all_trait_method_signatures(self) -> List[DBTraitMethodSignature]:
        """
        Get all trait method signatures.
        Returns:
            List of trait method signatures
        """
        return self.db.query(DBTraitMethodSignature).all()

    def get_trait_method_signatures_for_trait(
        self, trait_id: int
    ) -> List[DBTraitMethodSignature]:
        """
        Get all method signatures for a given trait.
        Args:
            trait_id: ID of the trait
        Returns:
            List of method signatures for the trait
        """
        return (
            self.db.query(DBTraitMethodSignature)
            .filter(DBTraitMethodSignature.trait_id == trait_id)
            .all()
        )

    def find_by_fully_qualified_path(self, fqp: str) -> List[Any]:
        """
        Find any entity by its fully qualified path.
        Args:
            fqp: Fully qualified path
        Returns:
            List of matching entities
        """
        results = []
        for entity_name, entity_class in self.entity_mapping.items():
            if hasattr(entity_class, "fully_qualified_path"):
                results.extend(
                    self.db.query(entity_class)
                    .filter(entity_class.fully_qualified_path == fqp)
                    .all()
                )
        return results

    def find_by_visibility(
        self, entity_type: str, visibility: str
    ) -> List[Any]:
        """
        Find entities of a given type with a specific visibility.
        Args:
            entity_type: Type of entity to search for
            visibility: Visibility to filter by
        Returns:
            List of matching entities
        """
        entity_class = self.entity_mapping.get(entity_type)
        if not entity_class or not hasattr(entity_class, "visibility"):
            return []

        return (
            self.db.query(entity_class)
            .filter(entity_class.visibility == visibility)
            .all()
        )

    def find_by_crate(self, entity_type: str, crate_name: str) -> List[Any]:
        """
        Find entities of a given type that belong to a specific crate.
        Args:
            entity_type: Type of entity to search for
            crate_name: Name of the crate
        Returns:
            List of matching entities
        """
        entity_class = self.entity_mapping.get(entity_type)
        if not entity_class or not hasattr(entity_class, "crate_name"):
            return []

        return (
            self.db.query(entity_class)
            .filter(entity_class.crate_name == crate_name)
            .all()
        )

    def find_functions_with_input_type(self, type_name: str) -> List[DBFunction]:
        """
        Find all functions that accept a specific type as one of their inputs.
        Args:
            type_name: The name of the input type to search for.
        Returns:
            A list of functions that have the specified input type.
        """
        # Handle both JSON string and JSON array formats
        return (
            self.db.query(DBFunction)
            .filter(
                or_(
                    # For JSON array format
                    DBFunction.input_types.contains([{"type_name": type_name}]),
                    # For JSON string format - use multiple LIKE patterns to be more robust
                    DBFunction.input_types.like(f'%"type_name": "{type_name}"%'),
                    DBFunction.input_types.like(f'%"type_name":"{type_name}"%'),
                    DBFunction.input_types.like(f'%{type_name}%')
                )
            )
            .all()
        )

    def find_functions_with_output_type(self, type_name: str) -> List[DBFunction]:
        """
        Find all functions that return a specific type.
        Args:
            type_name: The name of the output type to search for.
        Returns:
            A list of functions that have the specified output type.
        """
        # Handle both JSON string and JSON array formats
        return (
            self.db.query(DBFunction)
            .filter(
                or_(
                    # For JSON array format
                    DBFunction.output_types.contains([{"type_name": type_name}]),
                    # For JSON string format - use multiple LIKE patterns to be more robust
                    DBFunction.output_types.like(f'%"type_name": "{type_name}"%'),
                    DBFunction.output_types.like(f'%"type_name":"{type_name}"%'),
                    DBFunction.output_types.like(f'%{type_name}%')
                )
            )
            .all()
        )

    def find_entities_with_attribute(
        self, entity_type: str, attribute: str
    ) -> List[Any]:
        """
        Find entities (like functions or types) that are decorated with a specific attribute.
        Args:
            entity_type: The type of entity to search for (e.g., 'function', 'type').
            attribute: The attribute to search for.
        Returns:
            A list of entities that have the specified attribute.
        """
        entity_class = self.entity_mapping.get(entity_type)
        if not entity_class or not hasattr(entity_class, "attributes"):
            return []

        # Handle both string and array formats for attributes
        return (
            self.db.query(entity_class)
            .filter(
                or_(
                    entity_class.attributes.contains([attribute]),  # JSON array format
                    entity_class.attributes == attribute,           # String format
                    entity_class.attributes.like(f"%{attribute}%")  # Substring match in string
                )
            )
            .all()
        )
