from dataclasses import dataclass, field
from typing import List, Optional, Union, Any

@dataclass
class TypeExpr:
    name: str
    generics: List['TypeExpr'] = field(default_factory=list)

    def __str__(self):
        if not self.generics:
            return self.name
        return f"{self.name}<{', '.join(str(g) for g in self.generics)}>"

@dataclass
class ImportStmt:
    filename: str

@dataclass
class ConfigStmt:
    machine_name: str
    field_name: str
    type_expr: TypeExpr

@dataclass
class TypeDecl:
    name: str
    alias: Optional[TypeExpr] = None

@dataclass
class StructField:
    name: str
    type_expr: TypeExpr

@dataclass
class StructDecl:
    name: str
    fields: List[StructField]

@dataclass
class EventDecl:
    name: str
    params: List[tuple[str, TypeExpr]]

@dataclass
class FuncDecl:
    name: str
    params: List[tuple[str, TypeExpr]]
    return_type: TypeExpr
    is_nondet: bool = False
    body: Optional[List[Any]] = None

@dataclass
class Expr:
    pass

@dataclass
class ListExpr(Expr):
    elements: List[Expr]

@dataclass
class VarDecl:
    name: str
    type_expr: TypeExpr
    init_expr: Optional[Expr] = None

@dataclass
class IndexExpr(Expr):
    collection: str
    index: Expr


@dataclass
class BinOp(Expr):
    left: Expr
    op: str
    right: Expr

@dataclass
class CallExpr(Expr):
    name: str
    args: List[Expr]

@dataclass
class StructInitExpr(Expr):
    struct_name: str
    args: List[Expr]

@dataclass
class AtomExpr(Expr):
    value: Any

@dataclass
class Assignment:
    target: Union[str, IndexExpr]
    expr: Expr


@dataclass
class ExprStmt:
    expr: Expr

@dataclass
class ReturnStmt:
    expr: Expr

@dataclass
class IfStmt:
    condition: Expr
    body: List[Any]
    else_body: Optional[List[Any]] = None

@dataclass
class ForStmt:
    iter_var: str
    iterable: Expr
    body: List[Any]

@dataclass
class StructMatchField:
    name: str
    value: Any 

@dataclass
class StructMatch:
    name: str
    fields: List[StructMatchField]

@dataclass
class EventMatch:
    name: str
    args: List[Any]

@dataclass
class TransitionDecl:
    state_from: str
    event: EventMatch
    guard: Optional[Expr]
    state_to: str
    actions: List[Union[Assignment, ExprStmt, IfStmt, ForStmt]]

@dataclass
class MachineDecl:
    name: str
    params: List[tuple[str, TypeExpr]] = field(default_factory=list)
    vars: List[VarDecl] = field(default_factory=list)
    states: List[str] = field(default_factory=list)
    initial_state: str = ""
    transitions: List[TransitionDecl] = field(default_factory=list)
    funcs: List[FuncDecl] = field(default_factory=list)
    events: List[EventDecl] = field(default_factory=list)

@dataclass
class AssertStmt:
    expr: Expr

@dataclass
class TestDecl:
    name: str
    stmts: List[Union[Assignment, ExprStmt, AssertStmt, IfStmt, ForStmt]]

@dataclass
class Program:
    imports: List[ImportStmt] = field(default_factory=list)
    configs: List[ConfigStmt] = field(default_factory=list)
    types: List[TypeDecl] = field(default_factory=list)
    structs: List[StructDecl] = field(default_factory=list)
    events: List[EventDecl] = field(default_factory=list)
    funcs: List[FuncDecl] = field(default_factory=list)
    machines: List[MachineDecl] = field(default_factory=list)
    tests: List[TestDecl] = field(default_factory=list)
