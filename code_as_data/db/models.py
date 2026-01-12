from sqlalchemy import Column, Integer, String, Text, ForeignKey, Table, JSON, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .connection import Base
import os

# Use JSONB for PostgreSQL, JSON for other databases (like SQLite for testing)
def get_json_type():
    """Return JSONB for PostgreSQL, JSON for other databases."""
    db_url = os.getenv('DATABASE_URL', '')
    if 'postgresql' in db_url or 'postgres' in db_url:
        return JSONB
    return JSON

JSONType = get_json_type()

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

    # ---------- Rust additions ----------
    impl_blocks = relationship("ImplBlock",                back_populates="module")   # Rust specific
    constants   = relationship("Constant",                 back_populates="module")   # Rust specific
    trait_sigs  = relationship("TraitMethodSignature",     back_populates="module")   # Rust specific
    traits = relationship("Trait", back_populates="module")


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

    # ---------- Rust additions ----------
    fully_qualified_path = Column(String(1024))                       # Rust specific
    is_method            = Column(Boolean, default=False)             # Rust specific
    receiver_type        = Column(JSONType)                           # Rust specific
    input_types          = Column(JSONType)                           # Rust specific
    output_types         = Column(JSONType)                           # Rust specific
    line_number          = Column(Integer)                            # Rust specific
    column_number        = Column(Integer)                            # Rust specific
    origin_crate         = Column(String(255))                        # Rust specific
    origin_module        = Column(String(512))                        # Rust specific
    call_type            = Column(String(32))                         # Rust specific


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
    module_name = Column(String(255))
    line_number_start = Column(Integer)
    line_number_end = Column(Integer)
    type_enum = Column(String(512))
    instances_used = Column(Text, nullable=True)
    module_id = Column(Integer, ForeignKey("module.id"))


    # ---------- Rust additions ----------
    fully_qualified_path = Column(String(1024), index=True)          # Rust specific
    is_method            = Column(Boolean, default=False)            # Rust specific
    self_type            = Column(JSONType)                          # Rust specific
    input_types          = Column(JSONType)                          # Rust specific
    output_types         = Column(JSONType)                          # Rust specific
    types_used           = Column(JSONType)                          # Rust specific
    literals_used        = Column(JSONType)                          # Rust specific
    methods_called       = Column(JSONType)                          # Rust specific
    visibility           = Column(String(64))                        # Rust specific
    doc_comments         = Column(Text)                              # Rust specific
    attributes           = Column(JSONType)                          # Rust specific
    crate_name           = Column(String(255))                       # Rust specific
    module_path          = Column(String(512))                       # Rust specific



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
    impl_block_id = Column(Integer, ForeignKey("impl_block.id"))           # Rust specific
    impl_block    = relationship("ImplBlock", back_populates="methods")    # Rust specific


class WhereFunction(Base):
    """Table representing 'where' functions (nested within parent functions)."""

    __tablename__ = "where_function"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    function_signature = Column(Text, nullable=True)
    raw_string = Column(Text, nullable=True)
    src_loc = Column(String(512), nullable=True)
    parent_function_id = Column(Integer, ForeignKey("function.id"))


    # ---------- Rust additions ----------
    fully_qualified_path = Column(String(1024))               # Rust specific
    input_types          = Column(JSONType)                   # Rust specific
    output_types         = Column(JSONType)                   # Rust specific
    types_used           = Column(JSONType)                   # Rust specific
    literals_used        = Column(JSONType)                   # Rust specific
    methods_called       = Column(JSONType)                   # Rust specific
    is_method            = Column(Boolean, default=False)     # Rust specific
    self_type            = Column(JSONType)                   # Rust specific
    visibility           = Column(String(64))                 # Rust specific
    doc_comments         = Column(Text)                       # Rust specific
    attributes           = Column(JSONType)                   # Rust specific

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

    # ---------- Rust additions ----------
    path       = Column(Text)         # Rust specific  (raw 'use …' string)
    visibility = Column(String(64))   # Rust specific

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

    # ---------- Rust additions ----------
    fully_qualified_path = Column(String(1024))           # Rust specific
    fields               = Column(JSONType)               # Rust specific
    visibility           = Column(String(64))             # Rust specific
    doc_comments         = Column(Text)                   # Rust specific
    attributes           = Column(JSONType)               # Rust specific
    crate_name           = Column(String(255))            # Rust specific
    module_path          = Column(String(512))            # Rust specific


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


class ImplBlock(Base):
    __tablename__ = "impl_block"  # Rust specific

    id = Column(Integer, primary_key=True)              # Rust specific
    struct_name = Column(Text, index=True)              # Rust specific
    struct_fqp = Column(Text, index=True)               # Rust specific
    trait_name = Column(String(512), index=True)        # Rust specific
    trait_fqp = Column(String(1024), index=True)        # Rust specific
    src_location = Column(String(512))                  # Rust specific
    line_number_start = Column(Integer)                 # Rust specific
    line_number_end = Column(Integer)                   # Rust specific
    crate_name = Column(String(255))                    # Rust specific
    module_path = Column(String(512))                   # Rust specific
    module_name = Column(String(512))                   # Rust specific
    module_id = Column(Integer, ForeignKey("module.id"))# Rust specific
    trait_id = Column(Integer, ForeignKey("trait.id"))  # Rust specific

    module = relationship("Module", back_populates="impl_blocks")  # Rust specific
    methods = relationship("Function", back_populates="impl_block")  # Rust specific
    trait = relationship("Trait", back_populates="impl_blocks")    # Rust specific




class Constant(Base):
    __tablename__ = "constant"                        # Rust specific

    id                   = Column(Integer, primary_key=True)                         # Rust specific
    name                 = Column(String(255), index=True)                           # Rust specific
    fully_qualified_path = Column(String(1024))                                      # Rust specific
    const_type           = Column(JSONType)                                          # Rust specific
    src_location         = Column(String(512))                                       # Rust specific
    src_code             = Column(Text)                                              # Rust specific
    line_number_start    = Column(Integer)                                           # Rust specific
    line_number_end      = Column(Integer)                                           # Rust specific
    crate_name           = Column(String(255))                                       # Rust specific
    module_path          = Column(String(512))                                       # Rust specific
    visibility           = Column(String(255))                                       # Rust specific
    doc_comments         = Column(Text)                                              # Rust specific
    attributes           = Column(JSONType)                                          # Rust specific
    is_static            = Column(Boolean, default=False)                            # Rust specific
    module_id            = Column(Integer, ForeignKey("module.id"))                  # Rust specific

    module = relationship("Module", back_populates="constants")                      # Rust specific


class TraitMethodSignature(Base):
    __tablename__ = "trait_method_signature"         # Rust specific

    id                   = Column(Integer, primary_key=True)                         # Rust specific
    name                 = Column(String(255), index=True)                           # Rust specific
    fully_qualified_path = Column(String(1024))                                      # Rust specific
    input_types          = Column(JSONType)                                          # Rust specific
    output_types         = Column(JSONType)                                          # Rust specific
    src_location         = Column(String(512))                                       # Rust specific
    src_code             = Column(Text)                                              # Rust specific
    line_number_start    = Column(Integer)                                           # Rust specific
    line_number_end      = Column(Integer)                                           # Rust specific
    crate_name           = Column(String(255))                                       # Rust specific
    module_path          = Column(String(512))                                       # Rust specific
    module_name          = Column(String(512))                                       # Rust specific
    visibility           = Column(String(64))                                        # Rust specific
    doc_comments         = Column(Text)                                              # Rust specific
    attributes           = Column(JSONType)                                          # Rust specific
    is_async             = Column(Boolean, default=False)                            # Rust specific
    is_unsafe            = Column(Boolean, default=False)                            # Rust specific
    module_id            = Column(Integer, ForeignKey("module.id"))                  # Rust specific

    module = relationship("Module", back_populates="trait_sigs")                     # Rust specific

    trait_id = Column(Integer, ForeignKey("trait.id"))                     # Rust specific
    trait    = relationship("Trait", back_populates="methods")             # Rust specific


class Trait(Base):
    __tablename__ = "trait"

    id   = Column(Integer, primary_key=True)                               # Rust specific
    name = Column(String(255), index=True)                                 # Rust specific
    fully_qualified_path = Column(String(1024))                            # Rust specific
    src_location = Column(String(512))                                     # Rust specific
    module_name = Column(String(512))                                      # Rust specific
    module_path = Column(String(512))                                      # Rust specific
    crate_name = Column(String(255))                                       # Rust specific
    module_id    = Column(Integer, ForeignKey("module.id"))                # Rust specific

    module  = relationship("Module", back_populates="traits")              # Rust specific
    methods = relationship("TraitMethodSignature", back_populates="trait") # Rust specific
    impl_blocks = relationship("ImplBlock", back_populates="trait")        # Rust specific




# What to do in the importer
# When you create an ImplBlock row keep its DB id and set
# fn_row.impl_block_id = impl_block_id for every method inside the block.

# When you encounter a Trait item, insert a Trait row, grab its id, and set
# sig_row.trait_id = trait_id for each TraitMethodSignature inside that trait.

# If you don’t wire those IDs yet, the FK columns stay NULL and nothing breaks.
