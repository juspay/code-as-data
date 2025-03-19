from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, field_validator, Field as PydanticField, ConfigDict


class TypeOfType(str, Enum):
    """Enum representing different types of type definitions."""

    DATA = "data"
    SUMTYPE = "sumtype"
    TYPE = "type"
    NEWTYPE = "newtype"
    CLASS = "class"
    INSTANCE = "instance"

    @classmethod
    def resolve_value(cls, value: str) -> "TypeOfType":
        """Resolve a string to a TypeOfType value."""
        value = value.lower()
        if value == "data":
            return cls.DATA
        elif value == "type":
            return cls.TYPE
        elif value == "newtype":
            return cls.NEWTYPE
        elif value == "class":
            return cls.CLASS
        elif value == "instance":
            return cls.INSTANCE
        return cls.DATA


class TypeComponent(BaseModel):
    """Model representing a type component."""

    type_name: str


class TypeVariant(str, Enum):
    """Enum representing different variants of complex types."""

    ATOMIC = "AtomicType"
    LIST = "ListType"
    TUPLE = "TupleType"
    APP = "AppType"
    FUNC = "FuncType"
    FORALL = "ForallType"
    QUAL = "QualType"
    KIND_SIG = "KindSigType"
    BANG = "BangType"
    RECORD = "RecordType"
    PROMOTED_LIST = "PromotedListType"
    PROMOTED_TUPLE = "PromotedTupleType"
    LITERAL = "LiteralType"
    WILDCARD = "WildCardType"
    STAR = "StarType"
    IPARAM = "IParamType"
    DOC = "DocType"
    UNKNOWN = "UnknownType"


class ComplexType(BaseModel):
    """Model representing a complex type structure."""

    variant: TypeVariant
    # Fields for AtomicType
    atomic_component: Optional[TypeComponent] = None

    # Fields for ListType
    list_type: Optional["ComplexType"] = None

    # Fields for TupleType and PromotedTupleType
    tuple_types: Optional[List["ComplexType"]] = None

    # Fields for AppType
    app_func: Optional["ComplexType"] = None
    app_args: Optional[List["ComplexType"]] = None

    # Fields for FuncType
    func_arg: Optional["ComplexType"] = None
    func_result: Optional["ComplexType"] = None

    # Fields for ForallType
    forall_binders: Optional[List[TypeComponent]] = None
    forall_body: Optional["ComplexType"] = None

    # Fields for QualType
    qual_context: Optional[List["ComplexType"]] = None
    qual_body: Optional["ComplexType"] = None

    # Fields for KindSigType
    kind_type: Optional["ComplexType"] = None
    kind_sig: Optional["ComplexType"] = None

    # Fields for BangType
    bang_type: Optional["ComplexType"] = None

    # Fields for RecordType
    record_fields: Optional[List[Tuple[str, "ComplexType"]]] = None

    # Fields for PromotedListType
    promoted_list_types: Optional[List["ComplexType"]] = None

    # Fields for LiteralType
    literal_value: Optional[str] = None

    # Fields for IParamType
    iparam_name: Optional[str] = None
    iparam_type: Optional["ComplexType"] = None

    # Fields for DocType
    doc_type: Optional["ComplexType"] = None
    doc_string: Optional[str] = None

    # Field for UnknownType
    unknown_value: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class StructuredTypeRep(BaseModel):
    """Model representing a structured type representation."""

    raw_code: str
    structure: ComplexType

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TypeField(BaseModel):
    """Model representing a field in a type constructor."""

    field_name: str
    field_type: StructuredTypeRep

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Type(BaseModel):
    """Model representing a type definition."""

    type_name: str
    module_name: str
    line_number_start: int
    line_number_end: int
    data_constructors_list: List[Dict[str, Any]] = PydanticField(default_factory=list)
    type: TypeOfType = PydanticField(default=TypeOfType.DATA)
    cons: Dict[str, List[TypeField]] = PydanticField(default_factory=dict)
    raw_code: str
    src_loc: str

    model_config = ConfigDict(
        arbitrary_types_allowed=True, from_attributes=True, populate_by_name=True
    )

    @property
    def id(self) -> str:
        """Generate a unique ID for the type."""
        return f"{self.module_name}:{self.type_name}"

    def get_prompt(self) -> str:
        """Return the raw code for prompting."""
        return self.raw_code
