from sqlalchemy import Column, Integer, String, Text, ForeignKey, Table, JSON, Boolean
from sqlalchemy.orm import relationship
from .connection import Base

# Association table for many-to-many relationships
function_dependency = Table(
    "function_dependency",
    Base.metadata,
    Column("caller_id", Integer, ForeignKey("function.id"), primary_key=True),
    Column("callee_id", Integer, ForeignKey("function.id"), primary_key=True),
)

type_dependency = Table(
    "type_dependency",
    Base.metadata,
    Column("dependent_id", Integer, ForeignKey("type.id"), primary_key=True),
    Column("dependency_id", Integer, ForeignKey("type.id"), primary_key=True),
)


class Module(Base):
    """Table representing a code module."""

    __tablename__ = "module"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    path = Column(String(512))

    # Relationships
    functions = relationship("Function", back_populates="module")
    imports = relationship("Import", back_populates="module")
    types = relationship("Type", back_populates="module")
    classes = relationship("Class", back_populates="module")
    instances = relationship("Instance", back_populates="module")


class FunctionCalled(Base):
    """Table representing called functions."""

    __tablename__ = "function_called"

    id = Column(Integer, primary_key=True, index=True)
    module_name = Column(String(255))
    name = Column(Text)
    package_name = Column(String(255))
    src_loc = Column(String(512))
    _type = Column(Text)
    function_name = Column(Text)
    function_signature = Column(Text)
    type_enum = Column(Text)

    # Relationships
    function_id = Column(
        Integer, ForeignKey("function.id", ondelete="CASCADE"), nullable=True
    )
    function = relationship(
        "Function", back_populates="functions_called", foreign_keys=[function_id]
    )

    where_function_id = Column(
        Integer, ForeignKey("where_function.id", ondelete="CASCADE"), nullable=True
    )
    where_function = relationship(
        "WhereFunction",
        back_populates="functions_called",
        foreign_keys=[where_function_id],
    )


class Function(Base):
    """Table representing a function."""

    __tablename__ = "function"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    function_signature = Column(Text, nullable=True)
    raw_string = Column(Text, nullable=True)
    src_loc = Column(String(512), nullable=True)
    line_number_start = Column(Integer)
    line_number_end = Column(Integer)
    type_enum = Column(String(512))
    module_id = Column(Integer, ForeignKey("module.id"))

    # Input/output metadata
    function_input = Column(JSON, nullable=True)
    function_output = Column(JSON, nullable=True)

    # Relationships
    module = relationship("Module", back_populates="functions")
    where_functions = relationship(
        "WhereFunction", back_populates="parent_function", cascade="all, delete-orphan"
    )
    instance_functions = relationship("InstanceFunction", back_populates="function")

    # Add explicit relationship to functions_called
    functions_called = relationship(
        "FunctionCalled",
        back_populates="function",
        cascade="all, delete-orphan",
        foreign_keys="FunctionCalled.function_id",
    )

    # Self-referential many-to-many relationship for function calls
    called_functions = relationship(
        "Function",
        secondary=function_dependency,
        primaryjoin=id == function_dependency.c.caller_id,
        secondaryjoin=id == function_dependency.c.callee_id,
        backref="called_by",
    )


class WhereFunction(Base):
    """Table representing 'where' functions (nested within parent functions)."""

    __tablename__ = "where_function"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    function_signature = Column(Text, nullable=True)
    raw_string = Column(Text, nullable=True)
    src_loc = Column(String(512), nullable=True)
    parent_function_id = Column(Integer, ForeignKey("function.id"))

    # Relationships
    parent_function = relationship("Function", back_populates="where_functions")

    # Add relationship to functions_called
    functions_called = relationship(
        "FunctionCalled",
        back_populates="where_function",
        cascade="all, delete-orphan",
        foreign_keys="FunctionCalled.where_function_id",
    )


class Import(Base):
    """Table representing imports."""

    __tablename__ = "import"

    id = Column(Integer, primary_key=True, index=True)
    module_name = Column(String(255), nullable=True)
    package_name = Column(String(255), nullable=True)
    src_loc = Column(String(512))
    is_boot_source = Column(Boolean, default=False)
    is_safe = Column(Boolean, nullable=True)
    is_implicit = Column(Boolean, nullable=True)
    as_module_name = Column(String(255), nullable=True)
    qualified_style = Column(String(50), nullable=True)
    is_hiding = Column(Boolean, default=False)
    hiding_specs = Column(JSON, nullable=True)
    line_number_start = Column(Integer)
    line_number_end = Column(Integer)
    module_id = Column(Integer, ForeignKey("module.id"))

    # Relationships
    module = relationship("Module", back_populates="imports")


class Type(Base):
    """Table representing types."""

    __tablename__ = "type"

    id = Column(Integer, primary_key=True, index=True)
    type_name = Column(String(255), index=True)
    raw_code = Column(Text, nullable=True)
    src_loc = Column(String(512))
    type_of_type = Column(String(50))  # DATA, SUMTYPE, TYPE, NEWTYPE, CLASS, INSTANCE
    line_number_start = Column(Integer)
    line_number_end = Column(Integer)
    module_id = Column(Integer, ForeignKey("module.id"))

    # Relationships
    module = relationship("Module", back_populates="types")
    constructors = relationship("Constructor", back_populates="type")

    # Self-referential many-to-many relationship for type dependencies
    dependent_types = relationship(
        "Type",
        secondary=type_dependency,
        primaryjoin=id == type_dependency.c.dependent_id,
        secondaryjoin=id == type_dependency.c.dependency_id,
        backref="dependencies",
    )


class Constructor(Base):
    """Table representing type constructors."""

    __tablename__ = "constructor"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    type_id = Column(Integer, ForeignKey("type.id"))

    # Relationships
    type = relationship("Type", back_populates="constructors")
    fields = relationship("Field", back_populates="constructor")


class Field(Base):
    """Table representing constructor fields."""

    __tablename__ = "field"

    id = Column(Integer, primary_key=True, index=True)
    field_name = Column(String(255))
    field_type_raw = Column(Text)
    field_type_structure = Column(JSON, nullable=True)
    constructor_id = Column(Integer, ForeignKey("constructor.id"))

    # Relationships
    constructor = relationship("Constructor", back_populates="fields")


class Class(Base):
    """Table representing classes."""

    __tablename__ = "class"

    id = Column(Integer, primary_key=True, index=True)
    class_name = Column(String(255), index=True)
    class_definition = Column(Text)
    src_location = Column(String(512))
    line_number_start = Column(Integer)
    line_number_end = Column(Integer)
    module_id = Column(Integer, ForeignKey("module.id"))

    # Relationships
    module = relationship("Module", back_populates="classes")


class Instance(Base):
    """Table representing instances."""

    __tablename__ = "instance"

    id = Column(Integer, primary_key=True, index=True)
    instance_definition = Column(Text)
    instance_signature = Column(Text)
    src_loc = Column(String(512))
    line_number_start = Column(Integer)
    line_number_end = Column(Integer)
    module_id = Column(Integer, ForeignKey("module.id"))

    # Relationships
    module = relationship("Module", back_populates="instances")
    instance_functions = relationship("InstanceFunction", back_populates="instance")


class InstanceFunction(Base):
    """Table linking instances to their functions."""

    __tablename__ = "instance_function"

    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("instance.id"))
    function_id = Column(Integer, ForeignKey("function.id"))

    # Relationships
    instance = relationship("Instance", back_populates="instance_functions")
    function = relationship("Function", back_populates="instance_functions")
