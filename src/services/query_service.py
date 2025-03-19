from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from src.db.models import (
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
)


class QueryService:
    """Service for querying data from the database."""

    def __init__(self, db: Session):
        """
        Initialize the query service.

        Args:
            db: Database session
        """
        self.db = db

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
                joinedload(DBFunction.called_by),
                joinedload(DBFunction.module),
            )
            .filter(DBFunction.id == function_id)
            .first()
        )

        if not function:
            return None

        return {
            "id": function.id,
            "name": function.name,
            "signature": function.function_signature,
            "raw_string": function.raw_string,
            "src_loc": function.src_loc,
            "module": function.module.name,
            "where_functions": [
                {"id": wf.id, "name": wf.name, "signature": wf.function_signature}
                for wf in function.where_functions
            ],
            "calls": [
                {"id": cf.id, "name": cf.name, "module": cf.module.name}
                for cf in function.called_functions
            ],
            "called_by": [
                {"id": cb.id, "name": cb.name, "module": cb.module.name}
                for cb in function.called_by
            ],
        }

    def get_types_by_module(self, module_id: int) -> List[Dict[str, Any]]:
        """
        Get all types for a module with their constructors and fields.

        Args:
            module_id: ID of the module

        Returns:
            List of type dictionaries
        """
        types = (
            self.db.query(DBType)
            .options(joinedload(DBType.constructors).joinedload(DBConstructor.fields))
            .filter(DBType.module_id == module_id)
            .all()
        )

        result = []
        for type_obj in types:
            constructors = []
            for constructor in type_obj.constructors:
                constructors.append(
                    {
                        "name": constructor.name,
                        "fields": [
                            {"name": field.field_name, "type_raw": field.field_type_raw}
                            for field in constructor.fields
                        ],
                    }
                )

            result.append(
                {
                    "id": type_obj.id,
                    "name": type_obj.type_name,
                    "raw_code": type_obj.raw_code,
                    "type_of_type": type_obj.type_of_type,
                    "constructors": constructors,
                }
            )

        return result

    def get_type_by_name(
        self, name: str, module_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get types by name.

        Args:
            name: Name of the type
            module_id: Optional module ID filter

        Returns:
            List of matching type dictionaries
        """
        query = (
            self.db.query(DBType)
            .options(joinedload(DBType.constructors).joinedload(DBConstructor.fields))
            .filter(DBType.type_name == name)
        )

        if module_id:
            query = query.filter(DBType.module_id == module_id)

        types = query.all()

        result = []
        for type_obj in types:
            constructors = []
            for constructor in type_obj.constructors:
                constructors.append(
                    {
                        "name": constructor.name,
                        "fields": [
                            {"name": field.field_name, "type_raw": field.field_type_raw}
                            for field in constructor.fields
                        ],
                    }
                )

            result.append(
                {
                    "id": type_obj.id,
                    "name": type_obj.type_name,
                    "raw_code": type_obj.raw_code,
                    "type_of_type": type_obj.type_of_type,
                    "module": type_obj.module.name,
                    "constructors": constructors,
                }
            )

        return result

    def get_classes_by_module(self, module_id: int) -> List[DBClass]:
        """
        Get all classes for a module.

        Args:
            module_id: ID of the module

        Returns:
            List of classes
        """
        return self.db.query(DBClass).filter(DBClass.module_id == module_id).all()

    def get_class_by_name(
        self, name: str, module_id: Optional[int] = None
    ) -> List[DBClass]:
        """
        Get classes by name.

        Args:
            name: Name of the class
            module_id: Optional module ID filter

        Returns:
            List of matching classes
        """
        query = self.db.query(DBClass).filter(DBClass.class_name == name)
        if module_id:
            query = query.filter(DBClass.module_id == module_id)
        return query.all()

    def get_imports_by_module(self, module_id: int) -> List[DBImport]:
        """
        Get all imports for a module.

        Args:
            module_id: ID of the module

        Returns:
            List of imports
        """
        return self.db.query(DBImport).filter(DBImport.module_id == module_id).all()

    def get_instances_by_module(self, module_id: int) -> List[Dict[str, Any]]:
        """
        Get all instances for a module with their associated functions.

        Args:
            module_id: ID of the module

        Returns:
            List of instance dictionaries
        """
        instances = (
            self.db.query(DBInstance)
            .options(
                joinedload(DBInstance.instance_functions).joinedload(
                    DBInstanceFunction.function
                )
            )
            .filter(DBInstance.module_id == module_id)
            .all()
        )

        result = []
        for instance in instances:
            functions = []
            for inst_func in instance.instance_functions:
                function = inst_func.function
                functions.append(
                    {
                        "id": function.id,
                        "name": function.name,
                        "signature": function.function_signature,
                    }
                )

            result.append(
                {
                    "id": instance.id,
                    "definition": instance.instance_definition,
                    "signature": instance.instance_signature,
                    "src_loc": instance.src_loc,
                    "functions": functions,
                }
            )

        return result

    # Advanced queries

    def search_function_by_content(self, content: str) -> List[DBFunction]:
        """
        Search for functions containing specific content.

        Args:
            content: Content to search for

        Returns:
            List of matching functions
        """
        search_pattern = f"%{content}%"
        return (
            self.db.query(DBFunction)
            .filter(DBFunction.raw_string.ilike(search_pattern))
            .all()
        )

    def get_function_call_graph(
        self, function_id: int, depth: int = 1
    ) -> Dict[str, Any]:
        """
        Get a function call graph up to the specified depth.

        Args:
            function_id: ID of the function
            depth: Maximum depth of the call graph

        Returns:
            Dictionary representing the call graph
        """
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

        def build_graph(func, current_depth, max_depth):
            if current_depth > max_depth:
                return {
                    "id": func.id,
                    "name": func.name,
                    "module": func.module.name,
                    "calls": [],
                }

            calls = []
            for called in func.called_functions:
                calls.append(build_graph(called, current_depth + 1, max_depth))

            return {
                "id": func.id,
                "name": func.name,
                "module": func.module.name,
                "calls": calls,
            }

        return build_graph(function, 1, depth)

    def get_most_called_functions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most called functions.

        Args:
            limit: Maximum number of results

        Returns:
            List of function dictionaries with call counts
        """
        # This query uses a subquery to count incoming calls to each function
        from sqlalchemy.sql import select, func, alias

        # Create a subquery that counts incoming edges for each callee
        call_count = (
            self.db.query(
                func.count().label("calls"), DBFunction.id.label("function_id")
            )
            .join(DBFunction.called_by)
            .group_by(DBFunction.id)
            .subquery()
        )

        # Query functions with their call counts
        functions = (
            self.db.query(DBFunction, call_count.c.calls)
            .join(call_count, DBFunction.id == call_count.c.function_id)
            .order_by(call_count.c.calls.desc())
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
