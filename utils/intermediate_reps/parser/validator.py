from parser.ast_nodes import Program, TestDecl, Expr, AtomExpr, CallExpr, StructInitExpr, BinOp, Assignment, ExprStmt, AssertStmt, MachineDecl, IndexExpr

class ValidatorException(Exception):
    pass

class SemanticValidator:
    def __init__(self, program: Program):
        self.program = program
        self.machines = {m.name: m for m in program.machines}
        self.structs = {s.name: s for s in program.structs}
        self.funcs = {f.name: f for f in program.funcs}
        
        # Add machine functions
        for mac in program.machines:
            for f in mac.funcs:
                self.funcs[f.name] = f
        
        # Build set of all events explicitly declared in transitions or as machine events
        self.events = set()
        for mac in program.machines:
            for e in mac.events:
                self.events.add(e.name)
            for t in mac.transitions:
                self.events.add(t.event.name)
        
        # Built-in messaging/logging
        self.builtins = {"log", "choice", "len", "del"}

    def validate(self):
        """Perform a full semantic pass over the AST."""
        self._validate_machines()
        self._validate_tests()

    def _validate_machines(self):
        for mac in self.program.machines:
            for t in mac.transitions:
                self._validate_actions(t.actions, mac)
                if t.guard:
                    self._validate_expr(t.guard, {"__machine__": mac.name}, in_action=False)

    def _validate_tests(self):
        for test in self.program.tests:
            env_vars = set()
            for stmt in test.stmts:
                if isinstance(stmt, Assignment):
                    self._validate_expr(stmt.expr, env_vars, in_action=False)
                    if isinstance(stmt.target, IndexExpr):
                        self._validate_expr(stmt.target.index, env_vars, in_action=False)
                        env_vars.add(stmt.target.collection)
                    else:
                        env_vars.add(stmt.target)
                elif isinstance(stmt, ExprStmt):
                    self._validate_expr(stmt.expr, env_vars, in_action=False)
                elif isinstance(stmt, AssertStmt):
                    self._validate_expr(stmt.expr, env_vars, in_action=False)

    def _validate_actions(self, actions, mac: MachineDecl):
        """Validate an action block inside a machine transition limit context to machine attributes."""
        # Gather local context names
        local_vars = {ctx.name for ctx in mac.vars}
        for action in actions:
            if isinstance(action, Assignment):
                self._validate_expr(action.expr, local_vars, in_action=True)
                if isinstance(action.target, IndexExpr):
                    self._validate_expr(action.target.index, local_vars, in_action=True)
                    local_vars.add(action.target.collection)
                else:
                    local_vars.add(action.target)
            elif isinstance(action, ExprStmt):
                self._validate_expr(action.expr, local_vars, in_action=True)

    def _validate_expr(self, expr: Expr, env_vars: set, in_action: bool = False):
        if isinstance(expr, AtomExpr):
            # If it is a bare string identifier, check if it's a known identifier
            if isinstance(expr.value, str):
                val = expr.value
                if val.startswith('"') and val.endswith('"'):
                    return # String literal
                
                # Check property access var.prop
                if "." in val:
                    base = val.split(".")[0]
                    # We don't trace fields stringently yet, but base should exist
                elif val not in env_vars and val not in self.machines and not (val == "true" or val == "false"):
                    # For actions, config params might be in scope, but we do best effort check.
                    # We will be strict on tests though.
                    pass 
                
        elif isinstance(expr, CallExpr):
            # Ensure the function being called is known
            name_parts = expr.name.split('.')
            func_name = name_parts[-1]
            if func_name not in self.funcs and func_name not in self.builtins and func_name not in self.events and func_name not in self.machines and func_name not in self.structs:
                raise ValidatorException(f"Undefined function or event called: '{expr.name}'")
            
            for arg in expr.args:
                self._validate_expr(arg, env_vars, in_action)
                
        elif isinstance(expr, StructInitExpr):
            if expr.struct_name not in self.structs and expr.struct_name not in self.machines:
                raise ValidatorException(f"Undefined struct or machine initialized: '{expr.struct_name}'")
                
            for arg in expr.args:
                self._validate_expr(arg, env_vars, in_action)
                
        elif isinstance(expr, BinOp):
            self._validate_expr(expr.left, env_vars, in_action)
            self._validate_expr(expr.right, env_vars, in_action)
            
        elif isinstance(expr, IndexExpr):
            self._validate_expr(expr.index, env_vars, in_action)

