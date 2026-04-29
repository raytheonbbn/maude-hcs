from parser.ast_nodes import Program, MachineDecl, Expr, AtomExpr, CallExpr, StructInitExpr, BinOp, Assignment, ExprStmt, AssertStmt, IndexExpr, ListExpr, IfStmt, ForStmt, TypeExpr
import re

class MaudeTranspiler:
    def __init__(self, program: Program, config_params: dict = None):
        self.prog = program
        self.config_params = config_params or {}
        self.outputs = {}
        self.current_file = "index.maude"
        self._known_idents = set()
        self.for_helpers = []
        self.current_machine = None

    def emit(self, line: str):
        if self.current_file not in self.outputs:
            self.outputs[self.current_file] = []
        self.outputs[self.current_file].append(line)

    def _build_known_idents(self):
        """Collect every identifier name that should NOT be quoted in Maude output."""
        ki = self._known_idents
        for cfg in self.prog.configs:
            ki.add(cfg.machine_name + cfg.field_name)
        for s in self.prog.structs:
            ki.add(s.name)
        for f in self.prog.funcs:
            ki.add(f.name)
        for o in self.prog.events:
            ki.add(o.name)
        for mac in self.prog.machines:
            ki.add(mac.name)
            for c in mac.vars:
                ki.add(c.name)
            for s in mac.states:
                ki.add(s)
            for t in mac.transitions:
                ki.add(t.state_from)
                ki.add(t.state_to)
                for arg in t.event.args:
                    if isinstance(arg, tuple):
                        ki.add(arg[0])
                    elif hasattr(arg, 'name'):
                        ki.add(arg.name)
        ki.update(["INFO", "DEBUG", "WARN", "ERROR"])

    def _collect_events(self):
        """Collect all unique event signatures (name + param types)."""
        events = set() # set of (name, tuple(sorts))
        for e in self.prog.events:
            sorts = tuple(self._map_dsl_type(p[1]) for p in e.params)
            events.add((e.name, sorts))
        for mac in self.prog.machines:
            for e in mac.events:
                sorts = tuple(self._map_dsl_type(p[1]) for p in e.params)
                events.add((e.name, sorts))
        return events

    def _extract_rand_calls(self, expr, results=None):
        """Find all randInt(A, B) calls in an expression tree.
        Returns a list of (CallExpr, arg_exprs) tuples."""
        if results is None:
            results = []
        if isinstance(expr, CallExpr):
            # Check if this function is marked as nondet
            func = next((f for f in self.prog.funcs if f.name == expr.name), None)
            if func and func.is_nondet:
                results.append(expr)
            for a in expr.args:
                self._extract_rand_calls(a, results)
        elif isinstance(expr, StructInitExpr):
            for a in expr.args:
                self._extract_rand_calls(a, results)
        elif isinstance(expr, BinOp):
            self._extract_rand_calls(expr.left, results)
            self._extract_rand_calls(expr.right, results)
        return results

    def _map_dsl_type(self, type_expr):
        if hasattr(type_expr, "name"):
            type_name = type_expr.name
            generics = type_expr.generics
        else:
            type_name = type_expr
            generics = []

        mapping = {
            "Int": "Int", "Bool": "Bool", "String": "String", "Object": "Oid", "None": "Configuration"
        }
        
        if type_name == "List":
            if generics:
                inner = self._map_dsl_type(generics[0])
                return f"{inner}List"
            return "OidList"

        # Preserve struct types (Message, InFlight, etc.)
        struct_names = {s.name for s in self.prog.structs}
        if type_name in struct_names:
            return type_name
            
        # Map machine types to Oid
        machine_names = {m.name for m in self.prog.machines}
        if type_name in machine_names:
            return "Oid"
            
        return mapping.get(type_name, "String")

    def _infer_expr_type(self, expr, var_types=None):
        if var_types is None: var_types = {}
        if isinstance(expr, StructInitExpr):
            return expr.struct_name
        elif isinstance(expr, AtomExpr):
            if type(expr.value) is int: return "Int"
            elif type(expr.value) is bool: return "Bool"
            
            val = str(expr.value)
            # Check local var types
            if val in var_types: return str(var_types[val])
            
            # Check machine attributes
            if self.current_machine:
                attr = next((v for v in self.current_machine.vars if v.name == val), None)
                if attr: return str(attr.type_expr)
                
        elif isinstance(expr, ListExpr):
            if expr.elements:
                return f"List[{self._infer_expr_type(expr.elements[0], var_types)}]"
            return "List[Object]"
        elif isinstance(expr, CallExpr):
            struct_names = {s.name for s in self.prog.structs}
            if expr.name in struct_names:
                return expr.name
            if expr.name in ["getMap", "getMapL"]:
                return "OidList"
            func = next((f for f in self.prog.funcs if f.name == expr.name), None)
            if func:
                return self._map_dsl_type(func.return_type)
        elif isinstance(expr, IndexExpr):
            # Check for map access on machine attributes
            if self.current_machine:
                attr = next((v for v in self.current_machine.vars if v.name == expr.collection), None)
                if attr and hasattr(attr.type_expr, "generics") and attr.type_expr.generics:
                    inner_type = attr.type_expr.generics[1] # Map<Key, Val>
                    return self._map_dsl_type(inner_type)
            return "OidList" # Default for index/map
        elif isinstance(expr, BinOp):
            l_type = self._infer_expr_type(expr.left, var_types)
            if l_type == "Int": return "Int"
            if "List" in str(l_type): return l_type
        return "String"

    def _default_for_type(self, sort_name):
        if sort_name == "String": return '""'
        if sort_name == "Int": return "0"
        if sort_name == "Bool": return "false"
        if sort_name == "Oid": return "null"
        if sort_name == "Configuration": return "none"
        if sort_name.endswith("List"): return "nil"
        
        # Build default recursively if it's a known struct
        struct = next((s for s in self.prog.structs if s.name == sort_name), None)
        if struct:
            parts = [self._default_for_type(self._map_dsl_type(f.type_expr)) for f in struct.fields]
            return f'{sort_name}({", ".join(parts)})'
            
        return '""'

    def _get_midpoint_for_call(self, call_expr):
        """Calculate midpoint for choice messages based on randInt(A, B) arguments."""
        if not call_expr.args or len(call_expr.args) < 2:
            return 0
        min_val = self._evaluate_num_expr(call_expr.args[0])
        max_val = self._evaluate_num_expr(call_expr.args[1])
        return (min_val + max_val) // 2

    def _evaluate_num_expr(self, expr):
        """Try to resolve an expression to an integer (constant or config param)."""
        if isinstance(expr, AtomExpr):
            if isinstance(expr.value, int):
                return expr.value
            if isinstance(expr.value, str) and expr.value in self.config_params:
                val = self.config_params[expr.value]
                return val if isinstance(val, int) else 0
        return 0

    def _var_name_for_attr(self, attr_name):
        """Generate a Maude variable name for an attribute.
        Uses V$ prefix to avoid collisions with constructors like InFlight."""
        base = attr_name[0].upper() + attr_name[1:]
        # Check if it collides with a struct constructor name
        struct_names = {s.name for s in self.prog.structs}
        if base in struct_names:
            return f"{base}Val"
        return base

    def format_expr(self, expr, attr_vars=None, rand_subs=None, var_types=None):
        """Maude expression formatting. 
           attr_vars: mapping from attribute names to Maude variable names.
           rand_subs: mapping from CallExpr (id) back to OID-bind names for
                   non-deterministic substitution of randInt calls.
           var_types: mapping from local variable names to their DSL types.
        """
        if attr_vars is None:
            attr_vars = {}
        if rand_subs is None:
            rand_subs = {}
        if var_types is None:
            var_types = {}
            
        if isinstance(expr, AtomExpr):
            if type(expr.value) is int or type(expr.value) is float:
                return str(expr.value)
            if type(expr.value) is bool:
                return "true" if expr.value else "false"
            val = str(expr.value)
            
            # Already-quoted interpolated strings (from parser)
            if val.startswith('"') and val.endswith('"'):
                content = val[1:-1]
                if "{" in content:
                    # Split "Prefix {var} Suffix" into ("Prefix " + var + " Suffix")
                    parts = re.split(r'(\{.*?\})', content)
                    formatted_parts = []
                    for p in parts:
                        if p.startswith('{') and p.endswith('}'):
                            inner = p[1:-1]
                            # Handle len(var)
                            if inner.startswith("len(") and inner.endswith(")"):
                                var_name = inner[4:-1]
                                v_name = attr_vars.get(var_name, var_name)
                                formatted_parts.append(f"mToStr(size({v_name}))")
                            elif "." in inner:
                                bp, fp = inner.split(".", 1)
                                b_var = attr_vars.get(bp, bp)
                                b_type = var_types.get(bp)
                                t_name = b_type.name if hasattr(b_type, "name") else str(b_type)
                                # Extract field via projection function ONLY if bp is not a machine/Oid
                                is_machine = any(m.name == t_name for m in self.prog.machines)
                                if is_machine:
                                    formatted_parts.append(f"mToStr({b_var})")
                                else:
                                    formatted_parts.append(f"mToStr({fp}({b_var}))")
                            else:
                                v_name = attr_vars.get(inner, inner)
                                formatted_parts.append(f"mToStr({v_name})")
                        elif p:
                            formatted_parts.append(f'"{p}"')
                    if not formatted_parts: return '""'
                    if len(formatted_parts) == 1: return formatted_parts[0]
                    return f"({' + '.join(formatted_parts)})"
                return val
            
            # Handle dot-access like msg.prefix -> projection function
            if "." in val:
                parts = val.split(".")
                base = parts[0]
                field = parts[1]
                # Replace base with its variable name if available
                base_var = attr_vars.get(base, base)
                # Check type
                b_type = var_types.get(base)
                is_machine = False
                if b_type:
                    t_name = b_type.name if hasattr(b_type, "name") else str(b_type)
                    is_machine = any(m.name == t_name for m in self.prog.machines) or t_name in ["Oid", "String"]
                
                if is_machine:
                    return f"mToStr({base_var})"
                return f"{field}({base_var})"
            
            # Replace attribute references with their variable names
            if val in attr_vars:
                return attr_vars[val]
            
            # Check if this is a known identifier
            if val in self._known_idents:
                return val
            
            # Map log levels
            log_levels = {"LOG": "INFO", "INFO": "INFO", "DEBUG": "DEBUG", "WARN": "WARN", "ERROR": "ERROR"}
            if val in log_levels:
                return log_levels[val]

            # Determine whether to quote the value.
            # 1. Already quoted strings (e.g. from interpolation) or numbers stay as is.
            if val.startswith('"') or val.replace('.','',1).isdigit():
                return val
            
            # 2. Known identifiers (machines, states, events, constants) are NEVER quoted.
            if val in self._known_idents or val in getattr(self, "_oid_names", set()):
                return val
            
            # 3. Everything else is treated as a string literal and must be quoted.
            return f'"{val}"'
        elif isinstance(expr, CallExpr):
            # Check for non-deterministic substitution
            if id(expr) in rand_subs:
                return rand_subs[id(expr)]
            
            # Use mangled name for machine-specific functions
            func_name = expr.name
            if "." in expr.name:
                obj_name, method_name = expr.name.split(".", 1)
                obj_var = attr_vars.get(obj_name, obj_name)
                
                # Check for events (e.g. obj.event(args))
                event = None
                orig_obj_name = expr.name.split(".")[0]
                obj_type = self._infer_expr_type(AtomExpr(orig_obj_name), var_types)
                for mac in self.prog.machines:
                    if mac.name == obj_type or obj_type == "Oid":
                        event = next((e for e in mac.events if e.name == method_name), None)
                        if event: 
                            break
                
                # Check for machine-specific functions as a fallback if no event found
                if not event:
                    # Determine target machine from obj_type
                    target_mac = next((m for m in self.prog.machines if m.name == obj_type), None)
                    if target_mac:
                        m_func = next((f for f in target_mac.funcs if f.name == method_name), None)
                        if m_func:
                            method_name = f"{target_mac.name}-{method_name}"
                
                # Also check global events as fallback
                if not event:
                    event = next((e for e in self.prog.events if e.name == method_name), None)

                context_self = attr_vars.get("O", "O")
                context_sender = attr_vars.get("Sender", "Sender")

                if event:
                    # Events in Maude: Target, Sender, [Optional DSL Client Arg], Msg
                    # Our Maude signature for 'receive' is (Oid, Oid, Oid, Msg)
                    args = [obj_var, context_sender] # Target, Sender
                    # If the DSL call is obj.receive(msg) but event is (client, msg)
                    # then we have 2 DSL args but only 1 provided.
                    # We fill in 'O' (this) as the implicit client.
                    if len(expr.args) < len(event.params):
                         args.append(context_self)
                    
                    args.extend(self.format_expr(a, attr_vars, rand_subs, var_types) for a in expr.args)
                    return f"{method_name}({', '.join(args)})"
                
                args = [obj_var, context_sender]
                args.extend(self.format_expr(a, attr_vars, rand_subs, var_types) for a in expr.args)
                return f"{method_name}({', '.join(args)})"

            # Check if this is a machine function call (e.g. broadcast(...) in its own machine)
            for mac in self.prog.machines:
                func = next((f for f in mac.funcs if f.name == func_name), None)
                if func:
                    context_self = attr_vars.get("O", "O")
                    context_sender = attr_vars.get("Sender", "Sender")
                    args = [context_self, context_sender]
                    args.extend(self.format_expr(a, attr_vars, rand_subs, var_types) for a in expr.args)
                    return f"{mac.name}_{func_name}({', '.join(args)})"

            if func_name == "len":
                return f"size({self.format_expr(expr.args[0], attr_vars, rand_subs, var_types)})"
            if expr.name == "del":
                return f"del({self.format_expr(expr.args[0], attr_vars, rand_subs, var_types)}, {self.format_expr(expr.args[1], attr_vars, rand_subs, var_types)})"

            if not expr.args:
                return expr.name
            
            if expr.name == "log" and len(expr.args) >= 2:
                level = self.format_expr(expr.args[0], attr_vars, rand_subs, var_types)
                args = [level]
                for a in expr.args[1:]:
                    fmt_a = self.format_expr(a, attr_vars, rand_subs, var_types)
                    if fmt_a.startswith('"'):
                        args.append(fmt_a)
                    else:
                        args.append(f"mToStr({fmt_a})")
                return f"log({', '.join(args)})"
            
            args = ", ".join(self.format_expr(a, attr_vars, rand_subs, var_types) for a in expr.args)
            return f"{expr.name}({args})"
        elif isinstance(expr, ListExpr):
            if not expr.elements:
                return "nil"
            parts = [self.format_expr(e, attr_vars, rand_subs, var_types) for e in expr.elements]
            return f"({' '.join(parts)})"
        elif isinstance(expr, StructInitExpr):
            args = ", ".join(self.format_expr(a, attr_vars, rand_subs, var_types) for a in expr.args)
            return f"{expr.struct_name}({args})"
        elif isinstance(expr, BinOp):
            if expr.op == "+":
                left_type = self._infer_expr_type(expr.left, var_types)
                if "List" in str(left_type):
                    return f"({self.format_expr(expr.left, attr_vars, rand_subs, var_types)} {self.format_expr(expr.right, attr_vars, rand_subs, var_types)})"
            
            maude_op = "=/=" if expr.op == "!=" else expr.op
            return f"({self.format_expr(expr.left, attr_vars, rand_subs, var_types)} {maude_op} {self.format_expr(expr.right, attr_vars, rand_subs, var_types)})"
        elif isinstance(expr, IndexExpr):
            coll = attr_vars.get(expr.collection, expr.collection)
            idx = self.format_expr(expr.index, attr_vars, rand_subs, var_types)
            return f"getMap({coll}, {idx})"
        return str(expr)

    def _find_referenced_attrs(self, actions, guard, context_names, event_arg_names):
        """Find all context attribute names referenced in actions or guard (RHS/condition)."""
        referenced = set()
        for action in actions:
            if isinstance(action, Assignment):
                self._scan_expr_for_attrs(action.expr, context_names, event_arg_names, referenced)
            elif isinstance(action, ExprStmt):
                self._scan_expr_for_attrs(action.expr, context_names, event_arg_names, referenced)
        if guard:
            self._scan_expr_for_attrs(guard, context_names, event_arg_names, referenced)
        for action in actions:
            if isinstance(action, IfStmt):
                self._scan_expr_for_attrs(action.condition, context_names, event_arg_names, referenced)
                referenced.update(self._find_referenced_attrs(action.body, None, context_names, event_arg_names))
                if action.else_body:
                    referenced.update(self._find_referenced_attrs(action.else_body, None, context_names, event_arg_names))
            elif isinstance(action, ForStmt):
                self._scan_expr_for_attrs(action.iterable, context_names, event_arg_names, referenced)
                # iter_var is local, so we don't add it to referenced attrs if it's not a machine attr
                referenced.update(self._find_referenced_attrs(action.body, None, context_names, event_arg_names))
        return referenced

    def _scan_expr_for_attrs(self, expr, context_names, event_arg_names, result):
        """Recursively scan expression for references to context attributes."""
        if isinstance(expr, AtomExpr):
            val = str(expr.value) if type(expr.value) is str else ""
            # Check for direct reference
            if val in context_names and val not in event_arg_names:
                result.add(val)
            # Check in interpolated strings
            if val.startswith('"') and val.endswith('"'):
                content = val[1:-1]
                for match in re.findall(r'\{(.*?)\}', content):
                    v = match.split(".")[0]
                    if v in context_names and v not in event_arg_names:
                        result.add(v)
            # Check for dot-access base (e.g., "msg" from "msg.prefix")
            if "." in val:
                base = val.split(".")[0]
                if base in context_names and base not in event_arg_names:
                    result.add(base)
        elif isinstance(expr, CallExpr):
            if "." in expr.name:
                base = expr.name.split(".")[0]
                if base in context_names and base not in event_arg_names:
                    result.add(base)
            for a in expr.args:
                self._scan_expr_for_attrs(a, context_names, event_arg_names, result)
        elif isinstance(expr, StructInitExpr):
            for a in expr.args:
                self._scan_expr_for_attrs(a, context_names, event_arg_names, result)
        elif isinstance(expr, BinOp):
            self._scan_expr_for_attrs(expr.left, context_names, event_arg_names, result)
            self._scan_expr_for_attrs(expr.right, context_names, event_arg_names, result)
        elif isinstance(expr, IndexExpr):
            if expr.collection in context_names and expr.collection not in event_arg_names:
                result.add(expr.collection)
            self._scan_expr_for_attrs(expr.index, context_names, event_arg_names, result)

    def _apply_actions(self, actions, attr_current_expr, attr_vars, rand_subs, var_types=None):
        if var_types is None:
            var_types = {}
        emitted_outputs = []
        for action in actions:
            if isinstance(action, Assignment):
                current_attr_vars = {**attr_vars, **attr_current_expr}
                if isinstance(action.target, IndexExpr):
                    coll_name = action.target.collection
                    if coll_name in attr_current_expr:
                        idx_str = self.format_expr(action.target.index, current_attr_vars, rand_subs, var_types)
                        val_str = self.format_expr(action.expr, current_attr_vars, rand_subs, var_types)
                        attr_current_expr[coll_name] = f"putMap({attr_current_expr[coll_name]}, {idx_str}, {val_str})"
                else:
                    target_name = action.target
                    if target_name in attr_current_expr:
                        attr_current_expr[target_name] = self.format_expr(action.expr, current_attr_vars, rand_subs, var_types)
            elif isinstance(action, ExprStmt):
                expr = action.expr
                is_mutation = False
                if isinstance(expr, CallExpr):
                    if "." in expr.name:
                        base, method = expr.name.split(".", 1)
                        target_attr = base
                        call_method = method
                        args = expr.args
                    elif expr.name in ["del", "append"] and len(expr.args) > 0:
                        target_node = expr.args[0]
                        if isinstance(target_node, AtomExpr) and str(target_node.value) in attr_current_expr:
                            target_attr = str(target_node.value)
                            call_method = expr.name
                            args = expr.args[1:]
                            
                            current_attr_vars = {**attr_vars, **attr_current_expr}
                            if call_method == "append":
                                val = self.format_expr(args[0], current_attr_vars, rand_subs, var_types)
                                attr_current_expr[target_attr] = f"({attr_current_expr[target_attr]} ({val}))"
                                is_mutation = True
                            elif call_method == "del":
                                val = self.format_expr(args[0], current_attr_vars, rand_subs, var_types)
                                attr_current_expr[target_attr] = f"del({attr_current_expr[target_attr]}, {val})"
                                is_mutation = True
                        elif isinstance(target_node, IndexExpr) and target_node.collection in attr_current_expr:
                            target_attr = target_node.collection
                            call_method = expr.name
                            args = expr.args[1:]
                            
                            current_attr_vars = {**attr_vars, **attr_current_expr}
                            idx_str = self.format_expr(target_node.index, current_attr_vars, rand_subs, var_types)
                            
                            if call_method == "append":
                                val = self.format_expr(args[0], current_attr_vars, rand_subs, var_types)
                                old_coll = f"getMapL({attr_current_expr[target_attr]}, {idx_str})"
                                new_coll = f"({old_coll} ({val}))"
                                attr_current_expr[target_attr] = f"putMap({attr_current_expr[target_attr]}, {idx_str}, {new_coll})"
                                is_mutation = True
                            elif call_method == "del":
                                val = self.format_expr(args[0], current_attr_vars, rand_subs, var_types)
                                old_coll = f"getMapL({attr_current_expr[target_attr]}, {idx_str})"
                                new_coll = f"del({old_coll}, {val})"
                                attr_current_expr[target_attr] = f"putMap({attr_current_expr[target_attr]}, {idx_str}, {new_coll})"
                                is_mutation = True
                
                if not is_mutation:
                    current_attr_vars = {**attr_vars, **attr_current_expr}
                    formatted = self.format_expr(action.expr, current_attr_vars, rand_subs, var_types)
                    emitted_outputs.append(formatted)
            elif isinstance(action, IfStmt):
                current_attr_vars = {**attr_vars, **attr_current_expr}
                cond = self.format_expr(action.condition, current_attr_vars, rand_subs, var_types)
                
                # Copy current expr for both branches
                if_expr = dict(attr_current_expr)
                if_outputs = self._apply_actions(action.body, if_expr, attr_vars, rand_subs, var_types)
                
                else_expr = dict(attr_current_expr)
                else_outputs = []
                if action.else_body:
                    else_outputs = self._apply_actions(action.else_body, else_expr, attr_vars, rand_subs, var_types)
                
                # Merge attributes
                for name in attr_current_expr:
                    if if_expr[name] != else_expr[name]:
                        attr_current_expr[name] = f"(if {cond} then {if_expr[name]} else {else_expr[name]} fi)"
                
                # Merge outputs
                for out in if_outputs:
                    emitted_outputs.append(f"(if {cond} then {out} else none fi)")
                for out in else_outputs:
                    emitted_outputs.append(f"(if {cond} then none else {out} fi)")
            elif isinstance(action, ForStmt):
                # We need a helper for recursion. We'll register it to be emitted in the machine module.
                helper_id = f"{self.current_machine.name}For{len(self.for_helpers)}"
                coll_expr = self.format_expr(action.iterable, attr_vars, rand_subs, var_types)
                
                # We must pass the current state of ALL relevant variables to the helper
                # This includes attributes (potentially mutated) and event args.
                context_args = ["O", "Sender"]
                current_attr_vars = {**attr_vars, **attr_current_expr}
                
                # For now, let's just pass the attributes that are actually used in the body.
                # For now, let's just pass the attributes that are actually used in the body.
                # Find all used identifiers (excluding iterVar and O/Sender)
                def find_ids(node):
                    ids = set()
                    if isinstance(node, list):
                        for item in node: ids |= find_ids(item)
                        return ids
                    
                    if isinstance(node, AtomExpr):
                        val = str(node.value)
                        if "." in val: ids.add(val.split(".")[0])
                        else: ids.add(val)
                    elif isinstance(node, BinOp):
                        ids |= find_ids(node.left)
                        ids |= find_ids(node.right)
                    elif isinstance(node, CallExpr):
                        if "." in node.name: ids.add(node.name.split(".")[0])
                        for a in node.args: ids |= find_ids(a)
                    elif isinstance(node, Assignment):
                        if not isinstance(node.target, str):
                             ids |= find_ids(node.target.index)
                             ids.add(node.target.collection)
                        else: ids.add(node.target)
                        ids |= find_ids(node.expr)
                    elif isinstance(node, ExprStmt):
                        ids |= find_ids(node.expr)
                    elif isinstance(node, IfStmt):
                        ids |= find_ids(node.condition)
                        ids |= find_ids(node.body)
                        if node.else_body:
                            ids |= find_ids(node.else_body)
                    elif isinstance(node, ForStmt):
                        ids |= find_ids(node.iterable)
                        ids |= find_ids(node.body)
                    return ids

                body_ids = find_ids(action.body)
                
                sorted_vars = []
                # Include all attributes and locals that are used in the body
                for k, v in sorted(current_attr_vars.items()):
                    if k in body_ids and k != action.iter_var:
                        sorted_vars.append((k, v))
                
                pass_args = [v for k, v in sorted_vars]
                
                emitted_outputs.append(f"{helper_id}({coll_expr}, O, Sender, {', '.join(pass_args)})")
                
                self.for_helpers.append({
                    "id": helper_id,
                    "stmt": action,
                    "context_vars": [k for k, v in sorted_vars],
                    "var_types": var_types
                })
        return emitted_outputs

    def transpile(self) -> dict:
        self._build_known_idents()
        
        # Pre-scan tests for Oid nicks to use in mToStr
        self._oid_nicks = {}
        for test in self.prog.tests:
            for stmt in test.stmts:
                if isinstance(stmt, Assignment) and isinstance(stmt.expr, CallExpr):
                    # In our DSL, first arg is usually the nick/id string
                    if stmt.expr.args:
                        self._oid_nicks[stmt.target] = self.format_expr(stmt.expr.args[0])

        # 1. Types Module
        self.current_file = "PROTO-TYPES.maude"
        self.emit("mod PROTO-TYPES is")
        self.emit("  protecting INT .")
        self.emit("  protecting STRING .")
        self.emit("  protecting CONVERSION .")
        self.emit("  protecting BOOL .")
        self.emit("  protecting CONFIGURATION .") # For Oid
        self.emit("  subsort String < Oid .")
        
        # Add basic List support
        self.emit("  sort OidList .")
        self.emit("  subsort Oid < OidList .")
        self.emit("  op nil : -> OidList [ctor] .")
        self.emit("  op __ : OidList OidList -> OidList [ctor assoc id: nil] .")
        self.emit("  op size : OidList -> Int .")
        self.emit("  var L : OidList . var I : Oid .")
        self.emit("  eq size(nil) = 0 .")
        self.emit("  eq size(I L) = 1 + size(L) .")
        self.emit("  op del : OidList Oid -> OidList .")
        self.emit("  eq del(nil, I) = nil .")
        self.emit("  eq del(I L, I) = L .")
        self.emit("  eq del(I L, J:Oid) = I del(L, J:Oid) [owise] .")
        
        # string conversion helpers
        self.emit("  op mToStr : Oid -> String .")
        self.emit("  op mToStr : OidList -> String .")
        self.emit("  op mToStr : Int -> String .")
        self.emit("  op mToStr : String -> String .")
        self.emit("  var ConvS : String . var ConvN : Int . var ConvI : Oid . var ConvL : OidList .")
        self.emit("  eq mToStr(ConvI) = \"OID\" [owise] .")
        self.emit("  eq mToStr(ConvL) = \"LIST\" [owise] .")
        self.emit("  eq mToStr(ConvN) = string(ConvN, 10) .")
        self.emit("  eq mToStr(ConvS) = ConvS .")

        if self.prog.structs:
            struct_names = " ".join(s.name for s in self.prog.structs)
            self.emit(f"  sorts {struct_names} .")
            for s in self.prog.structs:
                ctor_types = " ".join(self._map_dsl_type(f.type_expr) for f in s.fields)
                self.emit(f"  op {s.name} : {ctor_types} -> {s.name} [ctor] .")
                self.emit(f"  op mToStr : {s.name} -> String .")
                self.emit(f"  eq mToStr(ConvST:{s.name}) = \"{s.name}Struct\" .")
            # Projection functions for struct field access
            emitted_proj_ops = set()
            for s in self.prog.structs:
                for idx, f in enumerate(s.fields):
                    ftype = self._map_dsl_type(f.type_expr)
                    proj_key = (f.name, s.name)
                    if proj_key not in emitted_proj_ops:
                        self.emit(f"  op {f.name} : {s.name} -> {ftype} .")
                        emitted_proj_ops.add(proj_key)
                # Generate projection equations with struct-scoped vars
                field_vars = []
                for idx, f in enumerate(s.fields):
                    ftype = self._map_dsl_type(f.type_expr)
                    vname = f"{s.name}F{idx}"
                    self.emit(f"  var {vname} : {ftype} .")
                    field_vars.append(vname)
                ctor_args = ", ".join(field_vars)
                for idx, f in enumerate(s.fields):
                    self.emit(f"  eq {f.name}({s.name}({ctor_args})) = {field_vars[idx]} .")

        self.emit("endm\n")

        # 2. System Module (Shared Events, Ops, and Logging)
        self.current_file = "PROTO-SYSTEM.maude"
        self.emit("omod PROTO-SYSTEM is")
        self.emit("  protecting PROTO-TYPES .")
        # Oid is now imported from PROTO-TYPES (via CONFIGURATION)
        self.emit("  ops null testOid : -> Oid .")

        # Collect Oid names dynamically from test assignments and event args
        oid_names = set()
        for test in self.prog.tests:
            for stmt in test.stmts:
                if isinstance(stmt, Assignment):
                    if isinstance(stmt.expr, CallExpr):
                        mac_name = stmt.expr.name
                        if any(m.name == mac_name for m in self.prog.machines):
                            oid_names.add(stmt.target)
                elif isinstance(stmt, ExprStmt) and isinstance(stmt.expr, CallExpr):
                    for a in stmt.expr.args:
                        if isinstance(a, AtomExpr) and type(a.value) is str:
                            # Don't add string literals (they start with '"' from parser)
                            if not a.value.startswith('"'):
                                 # If it has spaces, it's definitely a string literal, not a symbol/Oid
                                if " " not in a.value:
                                    oid_names.add(a.value)
        # Remove any names that are machine types or config names
        machine_names = {m.name for m in self.prog.machines}
        oid_names -= machine_names
        oid_names -= {c.machine_name + c.field_name for c in self.prog.configs}
        if oid_names:
            sorted_oids = sorted(oid_names)
            self.emit(f"  ops {' '.join(sorted_oids)} : -> Oid .")
            for oid in sorted_oids:
                pass

        # Store for use in test generation
        self._oid_names = oid_names

        # Aggregate and declare all events with correct types
        all_events = self._collect_events()
        for name, sorts in all_events:
            sorts_str = " ".join(sorts)
            self.emit(f"  op {name} : Oid Oid {sorts_str} -> Msg [ctor msg] .")
            if not sorts:
                # Add a 2-arg version for events called without DSL args if needed?
                # Actually Target and Sender are always there.
                pass

        # Logging
        self.emit("  sort LogLevel .")
        self.emit("  ops INFO DEBUG WARN ERROR : -> LogLevel .")
        self.emit("  op log : LogLevel String -> Configuration [ctor] .")
        self.emit("  op log : LogLevel String String -> Configuration [ctor] .")
        self.emit("  op log : LogLevel String String String -> Configuration [ctor] .")
        self.emit("  op log : LogLevel String String String String -> Configuration [ctor] .")
        
        # Maps (Simplified implementation for simulated collections)
        self.emit("  vars ConvS ConvS2 ConvS3 : String .")
        self.emit("  var ConvL2 : OidList .")
        self.emit("  op getMap : String String -> OidList .")
        self.emit("  op getMapL : String String -> OidList .") # Special version for List values
        self.emit("  eq getMap(ConvS, ConvS2) = nil [owise] .")
        self.emit("  eq getMapL(ConvS, ConvS2) = getMap(ConvS, ConvS2) .")
        self.emit("  op putMap : String String OidList -> String .")
        # For simulation, we can just treat the String as an abstract map term
        # or implement a real set of equations if needed. 
        # For simplicity, we'll let it stay as irreducible terms for now, 
        # BUT we MUST define how getMap interacts with putMap.
        self.emit("  eq getMap(putMap(ConvS, ConvS2, ConvL2), ConvS2) = ConvL2 .")
        self.emit("  eq getMap(putMap(ConvS, ConvS2, ConvL2), ConvS3) = getMap(ConvS, ConvS3) [owise] .")
        
        # OID to String conversion for all collected names
        # Use nick map if available to match DSL simulator behavior
        nick_map = getattr(self, '_oid_nicks', {})
        for oname in sorted(oid_names):
            display_name = nick_map.get(oname, oname)
            # Remove quotes if display_name came from a String literal
            if display_name.startswith('"') and display_name.endswith('"'):
                display_name = display_name[1:-1]
            self.emit(f"  eq mToStr({oname}) = \"{display_name}\" .")
        
        # Non-deterministic choice operator (binds a value on the LHS for rand* calls)
        self.emit("  op choice : Int -> Msg [ctor] .")
        self.emit("  op choice : String -> Msg [ctor] .")
        self.emit("  op choice : Oid -> Msg [ctor] .")

        # Functional Mocks — dynamically generated from DSL function declarations
        global_funcs = list(self.prog.funcs)
        # To avoid collisions, we can either prefix them or just collect them all.
        # But for now, let's just make sure we don't declare the same op twice.
        func_decls = {} # name -> (param_sorts, ret_sort, func_obj)
        
        for func in global_funcs:
            ps = [self._map_dsl_type(p[1]) for p in (func.params or [])]
            rs = self._map_dsl_type(func.return_type)
            func_decls[func.name] = (ps, rs, func)
            
        for mac in self.prog.machines:
            for func in mac.funcs:
                # Member functions include 'this' (O), 'sender', and all machine attributes
                attr_sorts = [self._map_dsl_type(v.type_expr) for v in mac.vars]
                ps = ["Oid", "Oid"] + attr_sorts + [self._map_dsl_type(p[1]) for p in (func.params or [])]
                rs = self._map_dsl_type(func.return_type)
                if rs == "None": rs = "Configuration"
                
                f_key = f"{mac.name}-{func.name}" # Mangle machine functions
                # Also store attribute names so we can map them in format_expr
                func_decls[f_key] = (ps, rs, func, [v.name for v in mac.vars])

        if func_decls:
            self.emit("  --- Functional Mocks")

            # Collect max vars per sort for equations
            max_vars_per_sort = {}
            for name, (param_sorts, ret_sort, func, *extra) in func_decls.items():
                attr_names = extra[0] if extra else []
                sc = {}
                for s in param_sorts:
                    sc[s] = sc.get(s, 0) + 1
                for s, count in sc.items():
                    max_vars_per_sort[s] = max(max_vars_per_sort.get(s, 0), count)

            mock_var_names = {}
            for sort, count in max_vars_per_sort.items():
                names = [f"Mock{sort}" if i == 0 else f"Mock{sort}{i}" for i in range(count)]
                mock_var_names[sort] = names
                self.emit(f"  var {' '.join(names)} : {sort} .")

            for name, (param_sorts, ret_sort, func, *extra) in func_decls.items():
                attr_names = extra[0] if extra else []
                if param_sorts:
                    self.emit(f"  op {name} : {' '.join(param_sorts)} -> {ret_sort} .")
                else:
                    self.emit(f"  op {name} : -> {ret_sort} .")

                sort_idx = {}
                p_vars = []
                for s in param_sorts:
                    idx = sort_idx.get(s, 0)
                    p_vars.append(mock_var_names[s][idx])
                    sort_idx[s] = idx + 1

                if getattr(func, 'is_nondet', False): continue
                
                # Setup context for function body transpilation
                l_vars = {}
                var_types = {}
                # In Maude, we added O and Sender as the first two args
                if param_sorts:
                    l_vars["O"] = p_vars[0]
                    l_vars["Sender"] = p_vars[1]
                    # Attributes follow O and Sender
                    for idx, a_name in enumerate(attr_names):
                        l_vars[a_name] = p_vars[idx+2]
                
                param_start = 2 + len(attr_names)
                for i, p in enumerate(func.params):
                    p_name, p_type = p
                    # parameters start after O, Sender, and attributes
                    l_vars[p_name] = p_vars[i+param_start] if param_sorts else p_vars[i]
                    var_types[p_name] = p_type
                
                
                # Check for body-less mock return
                if not getattr(func, 'body', None):
                    d_val = self._default_for_type(ret_sort)
                    if p_vars:
                        self.emit(f"  eq {name}({', '.join(p_vars)}) = {d_val} .")
                    else:
                        self.emit(f"  eq {name} = {d_val} .")
                else:
                    # Transpile the body as a sequence of actions.
                    # _apply_actions(self, actions, attr_current_expr, attr_vars, rand_subs, var_types=None)
                    body_acts = self._apply_actions(func.body, l_vars, {}, {}, var_types)
                    
                    # If it returns Configuration (None in DSL), concatenate all actions
                    if ret_sort == "Configuration":
                        rhs = " ".join(body_acts) if body_acts else "none"
                        self.emit(f"  eq {name}({', '.join(p_vars)}) = {rhs} .")
                    else:
                        # Find ReturnStmt if it returns a value
                        from parser.ast_nodes import ReturnStmt
                        ret_expr_maude = None
                        for stmt in func.body:
                            if isinstance(stmt, ReturnStmt):
                                ret_expr_maude = self.format_expr(stmt.expr, attr_vars=l_vars, var_types=var_types)
                                break
                        if not ret_expr_maude: 
                            ret_expr_maude = self._default_for_type(ret_sort)
                        self.emit(f"  eq {name}({', '.join(p_vars)}) = {ret_expr_maude} .")

        self.emit("endom")
        
        # Configuration Parameters
        if self.prog.configs:
            self.current_file = "PROTO-CONFIG.maude"
            self.emit("fmod PROTO-CONFIG is")
            self.emit("  protecting PROTO-TYPES .")
            self.emit("\n  --- Configuration Parameters")
            for cfg in self.prog.configs:
                target_sort = self._map_dsl_type(cfg.type_expr)
                param_name = f"{cfg.machine_name}.{cfg.field_name}"
                identifier = f"{cfg.machine_name}{cfg.field_name}"
                self.emit(f"  op {identifier} : -> {target_sort} .")
                if param_name in self.config_params:
                    val = self.config_params[param_name]
                    if target_sort == "String":
                        val = f'"{val}"'
                    self.emit(f"  eq {identifier} = {val} .")
                else:
                    raise Exception(f"Error: Required configuration '{param_name}' missing from YAML.")
            self.emit("endfm")

        if self.prog.machines:
            for mac in self.prog.machines:
                self.current_machine = mac
                self.for_helpers = []
                self.current_file = f"{mac.name}.maude"
                self.emit(f"omod {mac.name} is")
                self.emit("  protecting PROTO-SYSTEM .")
                if self.prog.configs:
                    self.emit("  protecting PROTO-CONFIG .")
                
                self.emit("  var O : Oid .")
                self.emit("  var Sender : Oid .")
                emitted_vars = set(["O", "Sender"])
                state_sort = f"{mac.name}State"
                self.emit(f"  sorts {state_sort} .")

                all_states = set(mac.states)
                if mac.initial_state:
                    all_states.add(mac.initial_state)
                for t in mac.transitions:
                    all_states.add(t.state_from)
                    all_states.add(t.state_to)

                if all_states:
                    states_str = " ".join(sorted(all_states))
                    self.emit(f"  ops {states_str} : -> {state_sort} .")

                # Build attribute type map
                attrs_decl = {}
                for c in mac.vars:
                    attrs_decl[c.name] = self._map_dsl_type(c.type_expr)
                for t in mac.transitions:
                    for a in t.actions:
                        if isinstance(a, Assignment):
                            t_name = a.target.collection if isinstance(a.target, IndexExpr) else a.target
                            if t_name not in attrs_decl:
                                # Fallback to String if type cannot be inferred
                                attrs_decl[t_name] = self._infer_expr_type(a.expr)

                attrs = [f"{mac.name}{k[0].upper()}{k[1:]} : {v}" for k, v in attrs_decl.items()]
                attrs_str = ", ".join(attrs)
                prefix = f", {attrs_str}" if attrs_str else ""
                self.emit(f"  class {mac.name} | currentState : {state_sort}{prefix} .")

                # Collect all attribute names for this machine
                all_attr_names = set(attrs_decl.keys())

                # Rewrite rules
                for i, t in enumerate(mac.transitions):
                    # Declare typed variables for event arguments
                    args_names = []
                    event_arg_names = set()
                    raw_to_mangled = {} # raw name -> mangled name
                    for arg in t.event.args:
                        if isinstance(arg, tuple):
                            raw_name = arg[0]
                            v_type = self._map_dsl_type(arg[1])
                        elif hasattr(arg, 'name'):
                            raw_name = arg.name
                            v_type = "String"
                        else:
                            raw_name = str(arg)
                            v_type = "String"
                        
                        v_name = f"V-{raw_name}-{v_type}"
                        raw_to_mangled[raw_name] = v_name

                        if v_name not in emitted_vars:
                            if v_type == "Int":
                                self.emit(f"  var {v_name} : Int .")
                            elif v_type == "Bool":
                                self.emit(f"  var {v_name} : Bool .")
                            elif v_type.endswith("List"):
                                self.emit(f"  var {v_name} : {v_type} .")
                            else:
                                self.emit(f"  var {v_name} : {v_type} .")
                            emitted_vars.add(v_name)
                        args_names.append(v_name)
                        event_arg_names.add(v_name)

                    # Find which attributes are referenced in the RHS/guard
                    referenced_attrs = self._find_referenced_attrs(
                        t.actions, t.guard, all_attr_names, event_arg_names
                    )

                    # Build attr_vars and var_types
                    attr_vars = {}
                    var_types = {}
                    for arg in t.event.args:
                        if isinstance(arg, tuple):
                            raw_name, dsl_type = arg
                            var_types[raw_name] = dsl_type
                            v_type = self._map_dsl_type(dsl_type)
                            attr_vars[raw_name] = f"V-{raw_name}-{v_type}"
                        elif hasattr(arg, 'name'): # For simple string args
                            raw_name = arg.name
                            var_types[raw_name] = "String"
                            attr_vars[raw_name] = raw_to_mangled[raw_name]
                        else: # For other simple args
                            raw_name = str(arg)
                            var_types[raw_name] = "String"
                            attr_vars[raw_name] = raw_to_mangled.get(raw_name, raw_name)
                    for attr_name in referenced_attrs:
                        if attr_name not in attr_vars:
                            var_name = self._var_name_for_attr(attr_name)
                            # Avoid collision with local vars
                            while var_name in event_arg_names:
                                var_name = f"A-{var_name}"
                            attr_vars[attr_name] = var_name
                            attr_type = attrs_decl.get(attr_name, "String")
                            var_types[attr_name] = attr_type # Store best known type
                            if var_name not in emitted_vars:
                                self.emit(f"  var {var_name} : {attr_type} .")
                                emitted_vars.add(var_name)

                    # --- Non-deterministic substitution for nondet calls ---
                    rand_subs = {}  # id(CallExpr) -> fresh var name
                    rand_constraints = []  # list of constraint strings
                    rand_choice_vars = []  # list of (var_name, ret_sort)
                    rand_counter = 0
                    for action in t.actions:
                        if isinstance(action, Assignment):
                            rand_calls = self._extract_rand_calls(action.expr)
                            for rc in rand_calls:
                                ret_sort = self._map_dsl_type(
                                    next((f.return_type.name for f in self.prog.funcs if f.name == rc.name), "Int")
                                )
                                var_name = f"Rand{ret_sort}{rand_counter}"
                                rand_counter += 1
                                rand_subs[id(rc)] = var_name
                                rand_choice_vars.append((var_name, ret_sort))
                                if var_name not in emitted_vars:
                                    self.emit(f"  var {var_name} : {ret_sort} .")
                                    emitted_vars.add(var_name)
                                # Build constraints from args (e.g., randInt(minDelay, maxDelay))
                                if len(rc.args) == 2:
                                    lo = self.format_expr(rc.args[0], attr_vars)
                                    hi = self.format_expr(rc.args[1], attr_vars)
                                    rand_constraints.append(f"{var_name} >= {lo}")
                                    rand_constraints.append(f"{var_name} <= {hi}")

                    rule_type = "crl" if t.guard or rand_constraints else "rl"
                    
                    self.emit(f"  {rule_type} [{mac.name}-{t.event.name}-{i}] :")

                    # LHS — include matched attributes + choice messages for rand vars
                    args = ", ".join(args_names)
                    if len(t.event.args) == 0:
                        lhs_evt = f"{t.event.name}(O, Sender) "
                    else:
                        lhs_evt = f"{t.event.name}(O, Sender, {args}) "

                    # Add choice(RandDn) for each non-deterministic variable
                    choice_lhs_parts = []
                    for (vname, _vsort) in rand_choice_vars:
                        choice_lhs_parts.append(f"choice({vname})")

                    lhs_attrs = []
                    for attr_name in referenced_attrs:
                        var_name = attr_vars[attr_name]
                        mang_name = f"{mac.name}{attr_name[0].upper()}{attr_name[1:]}"
                        lhs_attrs.append(f"{mang_name} : {var_name}")
                    lhs_attrs_str = ", ".join(lhs_attrs)
                    lhs_prefix = f", {lhs_attrs_str}" if lhs_attrs_str else ""

                    choice_str = " ".join(choice_lhs_parts)
                    if choice_str:
                        self.emit(f"    {lhs_evt}{choice_str} < O : {mac.name} | currentState : ({t.state_from}).{mac.name}State{lhs_prefix} >")
                    else:
                        self.emit(f"    {lhs_evt}< O : {mac.name} | currentState : ({t.state_from}).{mac.name}State{lhs_prefix} >")
                    self.emit("    =>")

                    # RHS — with rand substitutions applied
                    # Aggregate mutations per attribute to handle multiple updates correctly
                    attr_init_state = {name: attr_vars.get(name, name) for name in all_attr_names}
                    attr_current_expr = dict(attr_init_state)
                    
                    emitted_outputs = self._apply_actions(t.actions, attr_current_expr, attr_vars, rand_subs, var_types)

                    mutations = []
                    for name, expr in attr_current_expr.items():
                        # Only emit if it changed or if it's always required?
                        # For Maude objects, we only NEED to emit changed attributes, 
                        # but it's safer to emit all if they were matched.
                        if expr != attr_init_state.get(name, name):
                            mang_name = f"{mac.name}{name[0].upper()}{name[1:]}"
                            mutations.append(f"{mang_name} : {expr}")

                    mutations_str = ", ".join(mutations)
                    prefix_mut = f", {mutations_str}" if mutations_str else ""

                    self.emit(f"    < O : {mac.name} | currentState : ({t.state_to}).{mac.name}State{prefix_mut} >")
                    for out in emitted_outputs:
                        self.emit(f"    {out}")

                    # Condition: guard + non-deterministic constraints
                    conditions = []
                    if t.guard:
                        conditions.append(self.format_expr(t.guard, attr_vars, rand_subs, var_types))
                    conditions.extend(rand_constraints)
                    if conditions:
                        cond_str = " /\\ ".join(conditions)
                        self.emit(f"    if {cond_str} .")
                    else:
                        self.emit("    .")

                # Emit for_helpers for this machine
                for helper in self.for_helpers:
                    from typing import cast
                    hid = helper["id"]
                    stmt = cast(ForStmt, helper["stmt"])
                    ctx = helper["context_vars"] # List of strings
                    v_types = helper["var_types"]
                    
                    iter_var = stmt.iter_var
                    coll_type = self._map_dsl_type(self._infer_expr_type(stmt.iterable))
                    # Assume OidList for now if it is a list
                    if "List" in coll_type:
                        elem_type = coll_type.replace("List", "")
                    else:
                        elem_type = "Oid" 
                        coll_type = "OidList"

                    # Op declaration: coll context_vars -> Configuration
                    # hid : CollType Oid Sender (ContextVarTypes) -> Configuration
                    arg_types = ["Oid", "Oid"] # Self and Sender
                    for vname in ctx:
                        arg_types.append(self._map_dsl_type(v_types.get(vname, "Oid")))
                    
                    self.emit(f"  op {hid} : {coll_type} {' '.join(arg_types)} -> Configuration .")
                    
                    v_names_rhs = ["O", "Sender"] + [f"V{hid}_{i+2}" for i in range(len(arg_types)-2)]

                    # Equation 1: base case nil
                    vars_str = ", ".join(v_names_rhs)
                    self.emit(f"  eq {hid}(nil, {vars_str}) = none .")
                    
                    # Equation 2: recursive case
                    # eq hid(I L, Self, Sender, C1, C2...) = (Body with I) hid(L, Self, Sender, C1, C2...)
                    if "LRec" not in emitted_vars:
                        self.emit(f"  var LRec : {coll_type} .")
                        emitted_vars.add("LRec")
                    if "IRec" not in emitted_vars:
                        self.emit(f"  var IRec : {elem_type} .")
                        emitted_vars.add("IRec")
                        
                    for i, sort in enumerate(arg_types):
                        vname = v_names_rhs[i]
                        if vname not in emitted_vars:
                            self.emit(f"  var {vname} : {sort} .")
                            emitted_vars.add(vname)
                    
                    # Map the body. The iter_var becomes IRec. 
                    # Other vars in ctx map to V-names.
                    body_attr_vars = {}
                    body_var_types = dict(v_types)
                    
                    # Try to find refined DSL type for IRec
                    body_var_types[iter_var] = "Oid" 
                    iterable_type = self._infer_expr_type(stmt.iterable)
                    if hasattr(iterable_type, "generics") and iterable_type.generics:
                        body_var_types[iter_var] = iterable_type.generics[0]
                    
                    for i, vname in enumerate(ctx):
                        body_attr_vars[vname] = v_names_rhs[i+2] # Skip Self/Sender 
                    
                    body_attr_vars[iter_var] = "IRec"
                    
                    # Body actions applied. 
                    # Since we want the output of the body, we call _apply_actions with empty attributes
                    body_outputs = self._apply_actions(stmt.body, {}, body_attr_vars, {}, body_var_types)
                    body_rhs = " ".join(body_outputs) if body_outputs else "none"
                    
                    self.emit(f"  eq {hid}(IRec LRec, {', '.join(v_names_rhs)}) = ({body_rhs}) {hid}(LRec, {', '.join(v_names_rhs)}) .")

                self.emit("endom")

        # 3. Test Suite
        if self.prog.tests:
            self.current_file = "PROTO-TESTS.maude"
            self.emit("\nomod PROTO-TESTS is")
            self.emit("  protecting PROTO-SYSTEM .")
            if self.prog.configs:
                self.emit("  protecting PROTO-CONFIG .")
            if self.prog.machines:
                for mac in self.prog.machines:
                    self.emit(f"  protecting {mac.name} .")
            
            # Declare variables for all potential attribute-derived pattern variables in assertions
            # We'll use V-objid-attrname format as generated in collect_and_replace_attrs
            produced_vars = set()
            for test in self.prog.tests:
                for stmt in test.stmts:
                    if isinstance(stmt, AssertStmt):
                        def find_all_attrs(expr):
                            if isinstance(expr, AtomExpr):
                                val = str(expr.value)
                                if "." in val:
                                    parts = val.split(".")
                                    obj_id, attr_raw = parts[0], parts[1]
                                    obj_type = None
                                    for s in test.stmts:
                                        if isinstance(s, Assignment) and s.target == obj_id:
                                            val_c = self.format_expr(s.expr)
                                            obj_type = val_c.split('(')[0]
                                            break
                                    if obj_type:
                                        v_name = f"V{obj_id}{attr_raw[0].upper()}{attr_raw[1:]}"
                                        if v_name not in produced_vars:
                                            mac_def = next((m for m in self.prog.machines if m.name == obj_type), None)
                                            attr_t = "Oid"
                                            if mac_def:
                                                if attr_raw == "state": attr_t = f"{mac_def.name}State"
                                                else:
                                                    attr_def = next((v for v in mac_def.vars if v.name == attr_raw), None)
                                                    if attr_def: attr_t = self._map_dsl_type(attr_def.type_expr)
                                            self.emit(f"  var {v_name} : {attr_t} .")
                                            produced_vars.add(v_name)
                            elif isinstance(expr, BinOp):
                                find_all_attrs(expr.left); find_all_attrs(expr.right)
                            elif isinstance(expr, CallExpr):
                                for a in expr.args: find_all_attrs(a)
                        find_all_attrs(stmt.expr)
            self.emit("endom\n")

            for t_idx, test in enumerate(self.prog.tests):
                test_name = test.name.replace('"', '')
                self.emit(f"--- Test: {test_name}")

                # Process test statements in segments.
                # Every assert trigger a 'search' from the cumulative config.
                setup_lines = []
                accumulated_config = [] # Messages/Triggers and Objects
                has_asserts = False

                test_local_vars = {} # Maps local identifiers to formatted values

                # Track OIDs declared in this test to help with pattern matching
                local_oids = {} # name -> machine type
                object_attrs = {} # obj_id -> {attr_name -> val_maude}
                self._oid_nicks = {} # name -> nick (from first arg of constructor)

                def process_test_stmts(stmts, current_local_vars):
                    nonlocal has_asserts
                    for stmt in stmts:
                        if isinstance(stmt, Assignment):
                            val = self.format_expr(stmt.expr, attr_vars=current_local_vars)
                            obj_type = val.split('(')[0]
                            
                            if isinstance(stmt.expr, CallExpr) and stmt.expr.args:
                                nick_expr = stmt.expr.args[0]
                                self._oid_nicks[stmt.target] = self.format_expr(nick_expr, attr_vars=current_local_vars)

                            mac = next((m for m in self.prog.machines if m.name == obj_type), None)
                            if mac:
                                obj_id = stmt.target
                                local_oids[obj_id] = obj_type
                                
                                attrs_prefix = ""
                                attr_vals = {}
                                for idx, c in enumerate(mac.vars):
                                    if isinstance(stmt.expr, CallExpr) and idx < len(stmt.expr.args):
                                        attr_vals[c.name] = self.format_expr(stmt.expr.args[idx], attr_vars=current_local_vars)
                                    else:
                                        attr_vals[c.name] = self._default_for_type(self._map_dsl_type(c.type_expr.name))
                                object_attrs[obj_id] = attr_vals
                                
                                for tr in mac.transitions:
                                    for act in tr.actions:
                                        if isinstance(act, Assignment):
                                            target_name = act.target.collection if isinstance(act.target, IndexExpr) else act.target
                                            if target_name not in attr_vals:
                                                attr_vals[target_name] = self._default_for_type(self._infer_expr_type(act.expr))
                                
                                if attr_vals:
                                    defaults = ", ".join(f'{mac.name}{n[0].upper()}{n[1:]} : {v}' for n, v in attr_vals.items())
                                    attrs_prefix = f", {defaults}"
                                
                                init_state = mac.initial_state if mac and mac.initial_state else "START"
                                obj_id_q = obj_id
                                init_conf_str = f'< {obj_id_q} : {mac.name} | currentState : ({init_state}).{mac.name}State{attrs_prefix} >'
                                accumulated_config.append(init_conf_str)
                            else:
                                current_local_vars[stmt.target] = val

                        elif isinstance(stmt, ExprStmt):
                            trigger_expr = stmt.expr
                            if isinstance(trigger_expr, CallExpr):
                                new_choices = []
                                for mac in self.prog.machines:
                                    for tr in mac.transitions:
                                        if tr.event.name == trigger_expr.name:
                                            for act in tr.actions:
                                                if isinstance(act, Assignment):
                                                    for rc in self._extract_rand_calls(act.expr):
                                                        ret_sort = self._map_dsl_type(next((f.return_type.name for f in self.prog.funcs if f.name == rc.name), "Int"))
                                                        if ret_sort == "Int":
                                                            new_choices.append(f"choice({self._get_midpoint_for_call(rc)})")
                                                        elif ret_sort == "String":
                                                            new_choices.append(f'choice("rand")')
                                                        else:
                                                            new_choices.append(f"choice({self._default_for_type(ret_sort)})")

                                if "." in trigger_expr.name:
                                    obj_name, method_name = trigger_expr.name.split(".", 1)
                                    obj_type = local_oids.get(obj_name, "Oid")
                                    target_mac = next((m for m in self.prog.machines if m.name == obj_type), None)
                                    
                                    extra_args = []
                                    if target_mac:
                                        m_func = next((f for f in target_mac.funcs if f.name == method_name), None)
                                        if m_func:
                                            method_name = f"{target_mac.name}-{method_name}"
                                            obj_vals = object_attrs.get(obj_name, {})
                                            for v_def in target_mac.vars:
                                                extra_args.append(obj_vals.get(v_def.name, self._default_for_type(self._map_dsl_type(v_def.type_expr))))
                                    
                                    obj_id = obj_name
                                    obj_id_q = obj_id
                                    dsl_var_types = {k: TypeExpr(v) for k, v in local_oids.items()}
                                    args = [self.format_expr(a, attr_vars=current_local_vars, var_types=dsl_var_types) for a in trigger_expr.args]
                                    
                                    final_args = [obj_id_q, "testOid"] + extra_args + args
                                    accumulated_config.append(f"{method_name}({', '.join(final_args)})")
                                else:
                                    accumulated_config.append(self.format_expr(trigger_expr, attr_vars=current_local_vars))

                                if new_choices:
                                    accumulated_config.extend(new_choices)

                        elif isinstance(stmt, AssertStmt):
                            self.emit(f"  --- Assert: {self.format_expr(stmt.expr)}")
                            objs_to_match = {}
                            
                            def collect_and_replace_attrs(expr):
                                if isinstance(expr, AtomExpr):
                                    val = str(expr.value)
                                    if "." in val:
                                        parts = val.split(".")
                                        obj_id, attr_raw = parts[0], parts[1]
                                        if obj_id in local_oids:
                                            obj_type = local_oids[obj_id]
                                            attr_name = "currentState" if attr_raw == "state" else f"{obj_type}{attr_raw[0].upper()}{attr_raw[1:]}"
                                            var_name = f"V{obj_id}{attr_raw[0].upper()}{attr_raw[1:]}"
                                            if obj_id not in objs_to_match: objs_to_match[obj_id] = {}
                                            objs_to_match[obj_id][attr_name] = var_name
                                            return var_name
                                elif isinstance(expr, BinOp):
                                    return f"({collect_and_replace_attrs(expr.left)} {expr.op} {collect_and_replace_attrs(expr.right)})"
                                elif isinstance(expr, CallExpr):
                                    mapped_args = [collect_and_replace_attrs(a) for a in expr.args]
                                    if expr.name == "len": return f"size({mapped_args[0]})"
                                    return f"{expr.name}({', '.join(mapped_args)})"
                                return self.format_expr(expr, attr_vars=current_local_vars)

                            cond_expr = collect_and_replace_attrs(stmt.expr)
                            has_asserts = True
                            
                            pattern_parts = []
                            for obj_id, attrs in objs_to_match.items():
                                obj_type = local_oids[obj_id]
                                obj_id_q = obj_id
                                attrs_pattern = ", ".join(f"{n} : {v}" for n, v in attrs.items())
                                pattern_parts.append(f"< {obj_id_q} : {obj_type} | {attrs_pattern}, AS-{obj_id}:AttributeSet >")
                            
                            pattern = " ".join(pattern_parts) + " REST:Configuration"
                            if not pattern_parts: pattern = "REST:Configuration"

                            init_conf = " ".join(accumulated_config)
                            search_cmd = f"search [1] {init_conf} =>* {pattern} such that ({cond_expr}) = true"
                            self.emit(f"{search_cmd} .")

                        elif isinstance(stmt, IfStmt):
                            cond_val = self.format_expr(stmt.condition, attr_vars=current_local_vars)
                            if cond_val == "true":
                                process_test_stmts(stmt.body, current_local_vars)
                            elif cond_val == "false" and stmt.else_body:
                                process_test_stmts(stmt.else_body, current_local_vars)

                        elif isinstance(stmt, ForStmt):
                            iterable_val = self.format_expr(stmt.iterable, attr_vars=current_local_vars)
                            
                            def split_maude_list(s):
                                if s == "nil" or s == "": return []
                                if s.startswith('(') and s.endswith(')'): s = s[1:-1]
                                parts = []; cur = []; depth = 0; in_quote = False
                                for ch in s.strip():
                                    if ch == '"': in_quote = not in_quote; cur.append(ch)
                                    elif ch == '(' and not in_quote: depth += 1; cur.append(ch)
                                    elif ch == ')' and not in_quote: depth -= 1; cur.append(ch)
                                    elif ch == ' ' and depth == 0 and not in_quote:
                                        if cur: parts.append("".join(cur)); cur = []
                                    else: cur.append(ch)
                                if cur: parts.append("".join(cur))
                                return parts
                                
                            for item in split_maude_list(iterable_val):
                                next_vars = current_local_vars.copy()
                                next_vars[stmt.iter_var] = item
                                process_test_stmts(stmt.body, next_vars)
                
                process_test_stmts(test.stmts, test_local_vars)

                if not has_asserts:
                    init_conf = " ".join(accumulated_config)
                    if not init_conf.strip():
                        init_conf = "none"
                    self.emit(f"rew {init_conf} .")

                self.emit("")

        for fname, lines in self.outputs.items():
            self.outputs[fname] = "\n".join(lines)
            
        # Create an index.maude
        index_lines = []
        index_lines.append("load PROTO-TYPES.maude .")
        index_lines.append("load PROTO-SYSTEM.maude .")
        if self.prog.configs:
            index_lines.append("load PROTO-CONFIG.maude .")
        if self.prog.machines:
            for mac in self.prog.machines:
                index_lines.append(f"load {mac.name}.maude .")
        if self.prog.tests:
            index_lines.append("load PROTO-TESTS.maude .")
        self.outputs["index.maude"] = "\n".join(index_lines)

        return self.outputs

def transpile_to_maude(prog: Program, config_params: dict = None) -> dict:
    t = MaudeTranspiler(prog, config_params)
    return t.transpile()
