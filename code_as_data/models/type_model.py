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
    module_name: str
    package_name: str


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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComplexType":
        def field_name_transform_type_component(d):
            return {
                "module_name": d.get("moduleName'", ""),
                "type_name": d.get("typeName'", ""),
                "package_name": d.get("packageName", ""),
            }

        def unwrap_array(contents):
            """Helper to unwrap potentially nested arrays while preserving structure"""
            if isinstance(contents, list):
                if len(contents) == 1 and isinstance(contents[0], dict):
                    return contents[0]
                return contents
            return contents

        if not isinstance(data, dict):
            if isinstance(data, str):
                try:
                    return cls.from_dict(json.loads(data))
                except Exception as e:
                    print(e)
            print(data)
            return cls(variant=TypeVariant.UNKNOWN, unknown_value=str(data))

        # Handle tag-based format
        if "tag" in data and "contents" in data:
            tag = data["tag"]
            contents = data["contents"]

            # Convert tag to TypeVariant format
            if tag.endswith("Type"):
                variant_name = tag
            else:
                variant_name = f"{tag}Type"

            try:
                variant = TypeVariant(variant_name)
            except ValueError:
                print(data)
                return cls(variant=TypeVariant.UNKNOWN, unknown_value=str(data))

            # Handle each type variant
            if variant == TypeVariant.ATOMIC:
                type_component = field_name_transform_type_component(contents)
                return cls(
                    variant=TypeVariant.ATOMIC,
                    atomic_component=TypeComponent(**type_component),
                )

            elif variant == TypeVariant.APP:
                if isinstance(contents, list):
                    app_func = contents[0]
                    app_args = []

                    # Handle arguments, which might be wrapped in an array
                    if len(contents) >= 2:
                        args = contents[1]
                        if isinstance(args, list):
                            # Unwrap each argument
                            app_args = [unwrap_array(arg) for arg in args]
                        else:
                            app_args = [args]

                    return cls(
                        variant=TypeVariant.APP,
                        app_func=cls.from_dict(app_func),
                        app_args=[cls.from_dict(arg) for arg in app_args],
                    )
                elif isinstance(contents, dict):
                    return cls(
                        variant=TypeVariant.APP,
                        app_func=cls.from_dict(contents.get("func", {})),
                        app_args=[
                            cls.from_dict(arg) for arg in contents.get("args", [])
                        ],
                    )
                return cls(
                    variant=TypeVariant.APP,
                    app_func=cls.from_dict(contents),
                    app_args=[],
                )
            elif variant == TypeVariant.FUNC:
                if isinstance(contents, list) and len(contents) >= 2:
                    return cls(
                        variant=TypeVariant.FUNC,
                        func_arg=cls.from_dict(contents[0]),
                        func_result=cls.from_dict(contents[1]),
                    )
                if isinstance(contents, dict):
                    return cls(
                        variant=TypeVariant.FUNC,
                        func_arg=cls.from_dict(contents.get("arg", {})),
                        func_result=cls.from_dict(contents.get("result", {})),
                    )
                print(data)
                return cls(variant=TypeVariant.UNKNOWN, unknown_value=str(data))

            elif variant == TypeVariant.FORALL:
                if isinstance(contents, dict):
                    return cls(
                        variant=TypeVariant.FORALL,
                        forall_binders=[
                            TypeComponent(**(field_name_transform_type_component(b)))
                            for b in contents.get("binders", [])
                        ],
                        forall_body=cls.from_dict(contents.get("body", {})),
                    )
                if isinstance(contents, list) and len(contents) >= 2:

                    return cls(
                        variant=TypeVariant.FORALL,
                        forall_binders=[
                            TypeComponent(**(field_name_transform_type_component(b)))
                            for b in contents[0]
                        ],
                        forall_body=cls.from_dict(contents[1]),
                    )

            elif variant == TypeVariant.QUAL:
                if isinstance(contents, dict):
                    return cls(
                        variant=TypeVariant.QUAL,
                        qual_context=[
                            cls.from_dict(c) for c in contents.get("context", [])
                        ],
                        qual_body=cls.from_dict(contents.get("body", {})),
                    )
                if isinstance(contents, list) and len(contents) >= 2:
                    return cls(
                        variant=TypeVariant.QUAL,
                        qual_context=[cls.from_dict(c) for c in contents[0]],
                        qual_body=cls.from_dict(contents[1]),
                    )

            elif variant == TypeVariant.KIND_SIG:
                if isinstance(contents, dict):
                    return cls(
                        variant=TypeVariant.KIND_SIG,
                        kind_type=cls.from_dict(contents.get("type", {})),
                        kind_sig=cls.from_dict(contents.get("kind", {})),
                    )
                if isinstance(contents, list) and len(contents) >= 2:
                    return cls(
                        variant=TypeVariant.KIND_SIG,
                        kind_type=cls.from_dict(contents[0]),
                        kind_sig=cls.from_dict(contents[1]),
                    )

            elif variant == TypeVariant.BANG:
                return cls(variant=TypeVariant.BANG, bang_type=cls.from_dict(contents))

            elif variant == TypeVariant.RECORD:
                if isinstance(contents, dict):
                    return cls(
                        variant=TypeVariant.RECORD,
                        record_fields=[
                            (k, cls.from_dict(v)) for k, v in contents.items()
                        ],
                    )
                print(data)
                return cls(variant=TypeVariant.UNKNOWN, unknown_value=str(data))
            elif variant == TypeVariant.LIST:
                # Handle both direct type contents and nested type structures
                return cls(variant=TypeVariant.LIST, list_type=cls.from_dict(contents))
            elif variant == TypeVariant.TUPLE:
                # Handle tuple contents as list of types
                if isinstance(contents, list):
                    return cls(
                        variant=TypeVariant.TUPLE,
                        tuple_types=[cls.from_dict(t) for t in contents],
                    )
                # Handle single type case
                return cls(
                    variant=TypeVariant.TUPLE, tuple_types=[cls.from_dict(contents)]
                )
            elif variant == TypeVariant.PROMOTED_LIST:
                if isinstance(contents, list):
                    return cls(
                        variant=TypeVariant.PROMOTED_LIST,
                        promoted_list_types=[cls.from_dict(t) for t in contents],
                    )
                return cls(
                    variant=TypeVariant.PROMOTED_LIST,
                    promoted_list_types=[cls.from_dict(contents)],
                )

            elif variant == TypeVariant.PROMOTED_TUPLE:
                if isinstance(contents, list):
                    return cls(
                        variant=TypeVariant.PROMOTED_TUPLE,
                        tuple_types=[cls.from_dict(t) for t in contents],
                    )
                return cls(
                    variant=TypeVariant.PROMOTED_TUPLE,
                    tuple_types=[cls.from_dict(contents)],
                )

            elif variant == TypeVariant.LITERAL:
                return cls(variant=TypeVariant.LITERAL, literal_value=str(contents))

            elif variant == TypeVariant.IPARAM:
                if isinstance(contents, list) and len(contents) >= 2:
                    return cls(
                        variant=TypeVariant.IPARAM,
                        iparam_name=str(contents[0]),
                        iparam_type=cls.from_dict(contents[1]),
                    )
                if isinstance(contents, dict):
                    return cls(
                        variant=TypeVariant.IPARAM,
                        iparam_name=contents.get("name", ""),
                        iparam_type=cls.from_dict(contents.get("type", {})),
                    )
            elif variant == TypeVariant.WILDCARD:
                # WildCard type doesn't need contents
                return cls(variant=TypeVariant.WILDCARD)

            elif variant == TypeVariant.STAR:
                # Star type doesn't need contents
                return cls(variant=TypeVariant.STAR)
            elif variant == TypeVariant.DOC:
                if isinstance(contents, list) and len(contents) >= 2:
                    return cls(
                        variant=TypeVariant.DOC,
                        doc_type=cls.from_dict(contents[0]),
                        doc_string=str(contents[1]),
                    )
                if isinstance(contents, dict):
                    return cls(
                        variant=TypeVariant.DOC,
                        doc_type=cls.from_dict(contents.get("type", {})),
                        doc_string=contents.get("doc", ""),
                    )

            elif variant in [TypeVariant.STAR, TypeVariant.WILDCARD]:
                return cls(variant=variant)
        print(data)
        return cls(variant=TypeVariant.UNKNOWN, unknown_value=str(data))

    def to_string(self) -> str:
        """Convert the complex type to a string representation"""
        if self.variant == TypeVariant.ATOMIC and self.atomic_component:
            return f"{self.atomic_component.type_name}"

        elif self.variant == TypeVariant.LIST and self.list_type:
            return f"[{self.list_type.to_string()}]"

        elif self.variant == TypeVariant.TUPLE and self.tuple_types:
            types_str = ", ".join(t.to_string() for t in self.tuple_types)
            return f"({types_str})"

        elif self.variant == TypeVariant.APP and self.app_func and self.app_args:
            args_str = " ".join(arg.to_string() for arg in self.app_args)
            return f"({self.app_func.to_string()} {args_str})"

        elif self.variant == TypeVariant.FUNC and self.func_arg and self.func_result:
            return f"({self.func_arg.to_string()} -> {self.func_result.to_string()})"

        elif (
            self.variant == TypeVariant.FORALL
            and self.forall_binders
            and self.forall_body
        ):
            binders = " ".join(b.type_name for b in self.forall_binders)
            return f"forall {binders}. {self.forall_body.to_string()}"

        elif self.variant == TypeVariant.QUAL and self.qual_context and self.qual_body:
            context = ", ".join(c.to_string() for c in self.qual_context)
            return f"({context}) => {self.qual_body.to_string()}"

        # Add more cases as needed
        return str(self.unknown_value) if self.unknown_value else "unknown"


class StructuredTypeRep(BaseModel):
    """Model representing a structured type representation."""

    raw_code: str
    structure: ComplexType

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_dict(cls, raw_code: str, type_data: Dict[str, Any]) -> "StructuredTypeRep":
        return cls(raw_code=raw_code, structure=ComplexType.from_dict(type_data))


class TypeField(BaseModel):
    """Model representing a field in a type constructor."""

    field_name: str
    field_type: StructuredTypeRep

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_dict(cls, name: str, type_data: Dict[str, Any]) -> "TypeField":
        try:
            structured_type = StructuredTypeRep.from_dict(
                raw_code=type_data.get("raw_code", ""),
                type_data=type_data.get("structure", type_data),
            )
            return cls(field_name=name, field_type=structured_type)
        except Exception as e:
            print(e)


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

    def __init__(self, **data):
        # Determine type based on data_constructors_list
        if "typeKind" in data:
            if len(data.get("data_constructors_list", [])) > 1:
                data["type"] = TypeOfType.SUMTYPE
            else:
                data["type"] = TypeOfType.resolve_value(data.get("typeKind"))

        # Process constructors
        if data.get("type") in [TypeOfType.DATA, TypeOfType.SUMTYPE, TypeOfType.TYPE]:
            cons = {}
            for data_constructor in data.get("data_constructors_list", []):
                constructor_name = data_constructor.get(
                    "dataConNames", data.get("type_name")
                )
                cons[constructor_name] = [
                    TypeField.from_dict(k, v)
                    for (k, v) in data_constructor.get("fields", {}).items()
                ]
            data["cons"] = cons

        super().__init__(**data)
