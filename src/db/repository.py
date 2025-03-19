from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any, Union

from .models import (
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
)

from src.models.function_model import Function
from src.models.import_model import Import
from src.models.type_model import Type, TypeField
from src.models.class_model import Class
from src.models.instance_model import Instance


class Repository:
    """Data access layer for database operations."""

    def __init__(self, db: Session):
        self.db = db

    # Module operations
    def create_module(self, name: str, path: str) -> DBModule:
        """Create a new module in the database."""
        db_module = DBModule(name=name, path=path)
        self.db.add(db_module)
        self.db.commit()
        self.db.refresh(db_module)
        return db_module

    def get_module_by_name(self, name: str) -> Optional[DBModule]:
        """Get a module by name."""
        return self.db.query(DBModule).filter(DBModule.name == name).first()

    def get_module_by_path(self, path: str) -> Optional[DBModule]:
        """Get a module by path."""
        return self.db.query(DBModule).filter(DBModule.path == path).first()

    def get_or_create_module(self, name: str, path: str) -> DBModule:
        """Get an existing module or create a new one."""
        db_module = self.get_module_by_name(name)
        if db_module is None:
            db_module = self.create_module(name, path)
        return db_module

    # Function operations
    def create_function(self, function: Function, module_id: int) -> DBFunction:
        """Create a new function in the database."""
        db_function = DBFunction(
            name=function.function_name,
            function_signature=function.function_signature,
            raw_string=function.raw_string,
            src_loc=function.src_loc,
            line_number_start=function.line_number_start,
            line_number_end=function.line_number_end,
            type_enum=function.type_enum,
            module_id=module_id,
            function_input=function.function_input,
            function_output=function.function_output,
        )
        self.db.add(db_function)
        self.db.commit()
        self.db.refresh(db_function)

        # Process where functions
        for where_name, where_func in function.where_functions.items():
            self.create_where_function(where_func, db_function.id)

        return db_function

    def create_where_function(
        self, where_function, parent_function_id: int
    ) -> DBWhereFunction:
        """Create a new where function in the database."""
        db_where_function = DBWhereFunction(
            name=where_function.function_name,
            function_signature=where_function.function_signature,
            raw_string=where_function.raw_string,
            src_loc=where_function.src_loc,
            parent_function_id=parent_function_id,
        )
        self.db.add(db_where_function)
        self.db.commit()
        self.db.refresh(db_where_function)
        return db_where_function

    def get_function_by_name_and_module(
        self, name: str, module_id: int
    ) -> Optional[DBFunction]:
        """Get a function by name and module ID."""
        return (
            self.db.query(DBFunction)
            .filter(DBFunction.name == name, DBFunction.module_id == module_id)
            .first()
        )

    def create_function_dependency(self, caller_id: int, callee_id: int) -> None:
        """Create a function dependency relationship."""
        stmt = function_dependency.insert().values(
            caller_id=caller_id, callee_id=callee_id
        )
        self.db.execute(stmt)
        self.db.commit()

    # Import operations
    def create_import(self, import_data: Import, module_id: int) -> DBImport:
        """Create a new import in the database."""
        db_import = DBImport(
            module_name=import_data.module_name,
            package_name=import_data.package_name,
            src_loc=import_data.src_loc,
            is_boot_source=import_data.is_boot_source,
            is_safe=import_data.is_safe,
            is_implicit=import_data.is_implicit,
            as_module_name=import_data.as_module_name,
            qualified_style=import_data.qualified_style,
            is_hiding=import_data.is_hiding,
            hiding_specs=import_data.hiding_specs,
            line_number_start=import_data.line_number_start,
            line_number_end=import_data.line_number_end,
            module_id=module_id,
        )
        self.db.add(db_import)
        self.db.commit()
        self.db.refresh(db_import)
        return db_import

    # Type operations
    def create_type(self, type_data: Type, module_id: int) -> DBType:
        """Create a new type in the database."""
        db_type = DBType(
            type_name=type_data.type_name,
            raw_code=type_data.raw_code,
            src_loc=type_data.src_loc,
            type_of_type=type_data.type.value,
            line_number_start=type_data.line_number_start,
            line_number_end=type_data.line_number_end,
            module_id=module_id,
        )
        self.db.add(db_type)
        self.db.commit()
        self.db.refresh(db_type)

        # Process constructors
        for cons_name, fields in type_data.cons.items():
            constructor = self.create_constructor(cons_name, db_type.id)

            # Process fields
            for field in fields:
                self.create_field(field, constructor.id)

        return db_type

    def create_constructor(self, name: str, type_id: int) -> DBConstructor:
        """Create a new constructor in the database."""
        db_constructor = DBConstructor(name=name, type_id=type_id)
        self.db.add(db_constructor)
        self.db.commit()
        self.db.refresh(db_constructor)
        return db_constructor

    def create_field(self, field: TypeField, constructor_id: int) -> DBField:
        """Create a new field in the database."""
        db_field = DBField(
            field_name=field.field_name,
            field_type_raw=field.field_type.raw_code,
            field_type_structure=(
                field.field_type.structure.model_dump()
                if field.field_type.structure
                else None
            ),
            constructor_id=constructor_id,
        )
        self.db.add(db_field)
        self.db.commit()
        self.db.refresh(db_field)
        return db_field

    def get_type_by_name_and_module(
        self, name: str, module_id: int
    ) -> Optional[DBType]:
        """Get a type by name and module ID."""
        return (
            self.db.query(DBType)
            .filter(DBType.type_name == name, DBType.module_id == module_id)
            .first()
        )

    # Class operations
    def create_class(self, class_data: Class, module_id: int) -> DBClass:
        """Create a new class in the database."""
        db_class = DBClass(
            class_name=class_data.class_name,
            class_definition=class_data.class_definition,
            src_location=class_data.src_location,
            line_number_start=class_data.line_number_start,
            line_number_end=class_data.line_number_end,
            module_id=module_id,
        )
        self.db.add(db_class)
        self.db.commit()
        self.db.refresh(db_class)
        return db_class

    def get_class_by_name_and_module(
        self, name: str, module_id: int
    ) -> Optional[DBClass]:
        """Get a class by name and module ID."""
        return (
            self.db.query(DBClass)
            .filter(DBClass.class_name == name, DBClass.module_id == module_id)
            .first()
        )

    # Instance operations
    def create_instance(self, instance_data: Instance, module_id: int) -> DBInstance:
        """Create a new instance in the database."""
        db_instance = DBInstance(
            instance_definition=instance_data.instanceDefinition,
            instance_signature=instance_data.instance_signature,
            src_loc=instance_data.src_loc,
            line_number_start=instance_data.line_number_start,
            line_number_end=instance_data.line_number_end,
            module_id=module_id,
        )
        self.db.add(db_instance)
        self.db.commit()
        self.db.refresh(db_instance)

        # Associate instance with its functions
        for function in instance_data.functions:
            db_function = self.get_function_by_name_and_module(
                function.function_name, module_id
            )
            if db_function:
                self.create_instance_function_association(
                    db_instance.id, db_function.id
                )

        return db_instance

    def create_instance_function_association(
        self, instance_id: int, function_id: int
    ) -> DBInstanceFunction:
        """Create an association between an instance and a function."""
        db_instance_function = DBInstanceFunction(
            instance_id=instance_id, function_id=function_id
        )
        self.db.add(db_instance_function)
        self.db.commit()
        self.db.refresh(db_instance_function)
        return db_instance_function
