import os
from lark import Lark, Transformer, v_args, Token
from typing import List, Any
from .ast_nodes import *

class DSLTransformer(Transformer):
    @v_args(inline=True)
    def type_expr(self, name: Token, *generics) -> TypeExpr:
        return TypeExpr(str(name), list(generics))

    @v_args(inline=True)
    def param(self, name: Token, type_expr: TypeExpr) -> tuple[str, TypeExpr]:
        return (str(name), type_expr)
        
    @v_args(inline=False)
    def param_list(self, params: list) -> List[tuple[str, TypeExpr]]:
        return params

    @v_args(inline=True)
    def import_stmt(self, filename: Token) -> ImportStmt:
        return ImportStmt(filename.value[1:-1])

    @v_args(inline=True)
    def config_stmt(self, machine_name: Token, field_name: Token, type_expr: TypeExpr) -> ConfigStmt:
        return ConfigStmt(str(machine_name), str(field_name), type_expr)

    @v_args(inline=True)
    def type_decl(self, name: Token, alias=None) -> TypeDecl:
        if isinstance(alias, Token):
            alias = TypeExpr(str(alias))
        return TypeDecl(str(name), alias)

    @v_args(inline=True)
    def struct_field(self, name: Token, type_expr: TypeExpr) -> StructField:
        return StructField(str(name), type_expr)

    @v_args(inline=False)
    def struct_decl(self, args: list) -> StructDecl:
        name = str(args[0])
        fields = args[1:]
        return StructDecl(name, fields)

    @v_args(inline=False)
    def event_decl(self, args: list) -> EventDecl:
        name = str(args[0])
        params = args[1] if len(args) > 1 and isinstance(args[1], list) else []
        return EventDecl(name, params)

    @v_args(inline=False)
    def func_decl(self, args: list) -> FuncDecl:
        # In Lark, if [NONDET] is missing, passing `args` involves a `None`
        nondet_tok = args[0]
        is_nondet = (nondet_tok is not None and nondet_tok.value == 'nondet')
            
        name = str(args[1])
        params = args[2] if args[2] is not None else []
        type_expr = args[3]
        
        body = None
        if len(args) > 4:
            body = args[4]
            
        return FuncDecl(name, params, type_expr, is_nondet, body)

    @v_args(inline=False)
    def var_decl(self, args: list) -> VarDecl:
        name = str(args[0])
        type_expr = args[1]
        init_expr = args[2] if len(args) > 2 else None
        return VarDecl(name, type_expr, init_expr)

    @v_args(inline=True)
    def state_decl(self, name: Token) -> tuple:
        return ('state', str(name))

    @v_args(inline=True)
    def initial_decl(self, name: Token) -> tuple:
        return ('initial', str(name))

    @v_args(inline=False)
    def fname(self, args: list) -> str:
        return ".".join(str(a) for a in args)

    @v_args(inline=True)
    def call_expr(self, name, expr_list=None) -> CallExpr:
        args = expr_list if expr_list else []
        fname = name.value if hasattr(name, "value") else str(name)
        return CallExpr(fname, args)

    @v_args(inline=True)
    def struct_init(self, name: Token, expr_list=None) -> StructInitExpr:
        args = expr_list if expr_list else []
        return StructInitExpr(str(name), args)

    @v_args(inline=False)
    def atom_expr(self, args: list) -> AtomExpr:
        if len(args) == 1:
            value = args[0]
            if value.type == 'STRING':
                return AtomExpr(value.value)
            elif value.type == 'NUMBER':
                return AtomExpr(int(value) if '.' not in value else float(value))
            return AtomExpr(str(value))
        else:
            return AtomExpr(".".join(str(a) for a in args))

    @v_args(inline=True)
    def bin_op(self, left: Expr, op: Token, right: Expr) -> BinOp:
        return BinOp(left, str(op), right)

    @v_args(inline=False)
    def expr_list(self, args: list) -> List[Expr]:
        return args

    @v_args(inline=False)
    def list_expr(self, args: list) -> ListExpr:
        if not args or args[0] is None:
            return ListExpr([])
        return ListExpr(args[0])

    @v_args(inline=False)
    def block(self, args: list) -> List[Any]:
        return args

    @v_args(inline=True)
    def for_stmt(self, iter_var: Token, iterable: Expr, body: List[Any]) -> ForStmt:
        return ForStmt(str(iter_var), iterable, body)

    @v_args(inline=True)
    def if_stmt(self, condition: Expr, body: List[Any], else_body: Optional[List[Any]] = None) -> IfStmt:
        return IfStmt(condition, body, else_body)

    @v_args(inline=False)
    def assign_target(self, args: list) -> Union[str, IndexExpr]:
        name = str(args[0])
        if len(args) > 1:
            return IndexExpr(name, args[1])
        return name

    @v_args(inline=True)
    def assignment(self, target: Union[str, IndexExpr], expr: Expr) -> Assignment:
        return Assignment(target, expr)

    @v_args(inline=False)
    def index_expr(self, args: list) -> IndexExpr:
        base = args[0].value if hasattr(args[0], "value") else str(args[0])
        return IndexExpr(base, args[1])

    @v_args(inline=True)
    def return_stmt(self, expr: Expr) -> ReturnStmt:
        return ReturnStmt(expr)

    @v_args(inline=True)
    def expr_stmt(self, expr: Expr) -> ExprStmt:
        return ExprStmt(expr)

    @v_args(inline=True)
    def struct_match_field(self, name: Token, value: Any) -> StructMatchField:
        if isinstance(value, Token):
            if value.type == 'STRING':
                value = value.value[1:-1]
            elif value.type == 'NUMBER':
                value = int(value) if '.' not in value else float(value)
            else:
                value = str(value)
        return StructMatchField(str(name), value)

    @v_args(inline=False)
    def struct_match_fields(self, args: list) -> List[StructMatchField]:
        return args

    @v_args(inline=False)
    def struct_match(self, args: list) -> StructMatch:
        name = str(args[0])
        fields = args[1] if len(args) > 1 else []
        return StructMatch(name, fields)

    @v_args(inline=True)
    def event_arg(self, *args) -> Any:
        if len(args) == 1:
            val = args[0]
            if isinstance(val, StructMatch):
                return val
            if isinstance(val, Token):
                if val.type == 'STRING':
                    return val.value[1:-1]
                return str(val)
        if len(args) == 2:
            return (str(args[0]), str(args[1]))

    @v_args(inline=False)
    def event_args(self, args: list) -> List[Any]:
        return args

    @v_args(inline=False)
    def event_match(self, args: list) -> EventMatch:
        name = str(args[0])
        event_args = args[1] if len(args) > 1 and isinstance(args[1], list) else []
        return EventMatch(name, event_args)

    @v_args(inline=True)
    def guard(self, expr: Expr) -> Expr:
        return expr

    @v_args(inline=False)
    def transition_decl(self, args: list) -> TransitionDecl:
        # Lark optional expansions might inject `None`
        clean_args = [a for a in args if a is not None]
        
        state_from = str(clean_args[0])
        event = clean_args[1]
        
        idx = 2
        guard = None
        if isinstance(clean_args[idx], Expr):
            guard = clean_args[idx]
            idx += 1
            
        state_to = str(clean_args[idx])
        idx += 1
        
        actions = clean_args[idx]
        return TransitionDecl(state_from, event, guard, state_to, actions)

    @v_args(inline=False)
    def machine_decl(self, args: list) -> MachineDecl:
        name = str(args[0])
        mac = MachineDecl(name=name)
        members = args[1:]
        
        if members and isinstance(members[0], list):
            mac.params = members[0]
            members = members[1:]
            
        for member in members:
            if isinstance(member, VarDecl):
                mac.vars.append(member)
            elif isinstance(member, tuple):
                if member[0] == 'state': mac.states.append(member[1])
                elif member[0] == 'initial': mac.initial_state = member[1]
            elif isinstance(member, TransitionDecl):
                mac.transitions.append(member)
            elif isinstance(member, FuncDecl):
                mac.funcs.append(member)
            elif isinstance(member, EventDecl):
                mac.events.append(member)
                
        if not mac.initial_state and mac.states:
            mac.initial_state = mac.states[0]
            
        return mac

    @v_args(inline=True)
    def assert_stmt(self, expr: Expr) -> AssertStmt:
        return AssertStmt(expr)
        
    @v_args(inline=False)
    def test_decl(self, args: list) -> TestDecl:
        name = args[0].value[1:-1] if hasattr(args[0], 'value') else str(args[0])
        stmts = args[1:]
        return TestDecl(name, stmts)

    @v_args(inline=False)
    def start(self, args: list) -> Program:
        prog = Program()
        for arg in args:
            if isinstance(arg, ImportStmt): prog.imports.append(arg)
            elif isinstance(arg, ConfigStmt): prog.configs.append(arg)
            elif isinstance(arg, TypeDecl): prog.types.append(arg)
            elif isinstance(arg, StructDecl): prog.structs.append(arg)
            elif isinstance(arg, EventDecl): prog.events.append(arg)
            elif isinstance(arg, FuncDecl): prog.funcs.append(arg)
            elif isinstance(arg, MachineDecl): prog.machines.append(arg)
            elif isinstance(arg, TestDecl): prog.tests.append(arg)
        return prog

def load_parser() -> Lark:
    grammar_path = os.path.join(os.path.dirname(__file__), 'grammar.lark')
    with open(grammar_path, 'r') as f:
        grammar = f.read()
    return Lark(grammar, parser='lalr', start='start', transformer=DSLTransformer())

def parse_dsl(code: str) -> Program:
    parser = load_parser()
    return parser.parse(code)

def parse_and_resolve(filepath: str, parsed_files=None) -> Program:
    if parsed_files is None:
        parsed_files = set()
        
    abs_path = os.path.abspath(filepath)
    if abs_path in parsed_files:
        return Program([], [], [], [], [], [], [], [])
    
    parsed_files.add(abs_path)
    base_dir = os.path.dirname(abs_path)
    
    with open(abs_path, "r") as f:
        code = f.read()
        
    try:
        prog = parse_dsl(code)
    except Exception as e:
        raise Exception(f"Error parsing file '{filepath}':\n{e}") from e
    
    merged_prog = Program(
        imports=[],
        configs=list(prog.configs) if hasattr(prog, 'configs') else [],
        types=list(prog.types) if hasattr(prog, 'types') else [],
        structs=list(prog.structs),
        events=list(prog.events),
        funcs=list(prog.funcs),
        machines=list(prog.machines),
        tests=list(prog.tests)
    )
    
    for imp in prog.imports:
        dep_path = os.path.join(base_dir, imp.filename)
        dep_prog = parse_and_resolve(dep_path, parsed_files)
        
        merged_prog.configs.extend(dep_prog.configs)
        merged_prog.types.extend(dep_prog.types)
        merged_prog.structs.extend(dep_prog.structs)
        merged_prog.events.extend(dep_prog.events)
        merged_prog.funcs.extend(dep_prog.funcs)
        merged_prog.machines.extend(dep_prog.machines)
        merged_prog.tests.extend(dep_prog.tests)
        
    return merged_prog

