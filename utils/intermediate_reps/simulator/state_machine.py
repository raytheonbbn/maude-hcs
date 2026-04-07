from parser.ast_nodes import Program, BinOp, CallExpr, StructInitExpr, AtomExpr, Assignment, ReturnStmt, ExprStmt, MachineDecl, TestDecl, AssertStmt, ListExpr, IfStmt, ForStmt, ReturnStmt, Expr, IndexExpr

class InterpreterException(Exception): pass

class DSLSimulator:
    def __init__(self, program: Program, config_params: dict = None):
        self.program = program
        self.config_params = config_params or {}
        self.machines = {m.name: m for m in program.machines}
        self.structs = {s.name: s for s in program.structs}
        self.funcs = {f.name: f for f in program.funcs}
        for mac in program.machines:
            for f in mac.funcs:
                self.funcs[f"{mac.name}.{f.name}"] = f
        self.tests_passed = 0
        self.tests_failed = 0
        self.event_queue = []

    def run_all(self):
        if not self.program.tests:
            return
            
        print("\n--- Running DSL Test Simulation ---")
        for test in self.program.tests:
            self.run_test(test)
            
        print(f"Simulation Complete: {self.tests_passed} Passed / {self.tests_failed} Failed\n")

    def eval_expr(self, expr: Expr, env: dict):
        if isinstance(expr, IndexExpr):
            coll = env.get(expr.collection)
            if coll is None and "__self__" in env and isinstance(env["__self__"], dict):
                coll = env["__self__"].get(expr.collection)
            if coll is None:
                coll = self.config_params.get(expr.collection)
            
            idx = self.eval_expr(expr.index, env)
            if isinstance(coll, dict):
                return coll.get(idx, None)
            elif hasattr(coll, "__getitem__"):
                return coll[idx]
            return None
        elif isinstance(expr, AtomExpr):
            if isinstance(expr.value, str):
                # If it's a quoted string literal, unquote it
                if expr.value.startswith('"') and expr.value.endswith('"'):
                    return expr.value[1:-1]
                
                # If __self__ exists, prefer it for names that live on the machine object.
                if "__self__" in env and isinstance(env["__self__"], dict) and expr.value in env["__self__"]:
                    return env["__self__"][expr.value]
                # Check variable reference (local params, loop vars, etc.)
                if expr.value in env:
                    return env[expr.value]
                if expr.value in self.config_params:
                    return self.config_params[expr.value]
                # Check property access `machine.state`
                if "." in expr.value:
                    parts = expr.value.split(".")
                    base = parts[0]
                    prop = parts[1]
                    if base in env and isinstance(env[base], dict):
                        return env[base].get(prop, expr.value)
            return expr.value
            
        elif isinstance(expr, StructInitExpr):
            # Create a dictionary representing the struct/machine state
            obj = {"__type__": expr.struct_name}
            
            # If it's a machine initialization
            if expr.struct_name in self.machines:
                mac = self.machines[expr.struct_name]
                obj["state"] = mac.initial_state
                obj["__is_machine__"] = True
            
            # Populate kwargs/args
            for i, arg in enumerate(expr.args):
                val = self.eval_expr(arg, env)
                if isinstance(arg, Assignment):
                    obj[arg.target] = self.eval_expr(arg.expr, env)
                elif expr.struct_name in self.structs:
                    s_decl = self.structs[expr.struct_name]
                    if i < len(s_decl.fields):
                        obj[s_decl.fields[i].name] = val
                        
            return obj
            

        elif isinstance(expr, CallExpr):
            # Check if this is a machine initialization parsed as a CallExpr
            if expr.name in self.machines:
                mac = self.machines[expr.name]
                obj = {"__type__": expr.name, "state": mac.initial_state, "__is_machine__": True}
                for idx, ctx in enumerate(mac.params):
                    if idx < len(expr.args):
                        obj[ctx[0]] = self.eval_expr(expr.args[idx], env)
                init_env = dict(env)
                init_env.update(obj)
                for ctx in mac.vars:
                    if ctx.init_expr:
                        obj[ctx.name] = self.eval_expr(ctx.init_expr, init_env)
                    elif ctx.type_expr and ctx.type_expr.name == "List":
                        obj[ctx.name] = []
                    else:
                        obj[ctx.name] = None
                return obj
            
            # Check if this is a struct initialization parsed as a CallExpr
            struct_def = next((s for s in self.program.structs if s.name == expr.name), None)
            if struct_def:
                obj = {"__type__": expr.name}
                for i, field in enumerate(struct_def.fields):
                    if i < len(expr.args):
                        obj[field.name] = self.eval_expr(expr.args[i], env)
                return obj
            
            # Check if it's a non-deterministic function
            func = next((f for f in self.program.funcs if f.name == expr.name), None)
            if func and getattr(func, "is_nondet", False):
                if hasattr(self, "current_test_nondets"):
                    self.current_test_nondets.add(expr.name)
                
                # Mock a return value based on declared type
                ret_type = func.return_type.name if getattr(func, "return_type", None) else "Int"
                if ret_type == "Int": return 42
                if ret_type == "String": return "rand_str"
                if ret_type == "Bool": return False
                return None

            # Evaluate arguments
            args = [self.eval_expr(a, env) for a in expr.args]
            
            target_obj = None
            func_name = expr.name
            if "." in expr.name:
                parts = expr.name.split(".")
                obj_name = parts[0]
                func_name = parts[1]
                if obj_name in env and isinstance(env[obj_name], dict):
                    target_obj = env[obj_name]
            else:
                if "__self__" in env and isinstance(env["__self__"], dict) and expr.name in [f.name for f in self.machines[env["__self__"]["__type__"]].funcs]:
                    target_obj = env["__self__"]
                    func_name = expr.name
                    
            if target_obj and target_obj.get("__is_machine__"):
                mac_decl = self.machines[target_obj["__type__"]]
                func = next((f for f in mac_decl.funcs if f.name == func_name), None)
                if func:
                    local_env = dict(env)
                    local_env["__self__"] = target_obj
                    for i, param in enumerate(func.params):
                        if i < len(args):
                            param_name = str(param[0])
                            local_env[param_name] = args[i]
                    self.exec_stmts(func.body, local_env, target_obj)
                    return None
                    
                caller = env.get("__self__")
                event_args = [target_obj]
                
                # Check target machine's EventDecl to decide if implicit caller is needed
                mac_decl = self.machines[target_obj["__type__"]]
                evt_decl = next((e for e in mac_decl.events if e.name == func_name), None)
                if evt_decl and caller:
                    # If event signature has one more parameter than passed explicitly, insert caller
                    if len(evt_decl.params) == len(args) + 1:
                        event_args.append(caller)
                
                event_args.extend(args)
                return {"__type__": "call", "name": func_name, "args": event_args}
            
            # Intercept built-in log output
            if expr.name == "log" and len(args) >= 2:
                level = args[0]
                msg = str(args[1])
                import re
                def repl(m):
                    var_name = m.group(1)
                    # Handle len(var) calls inside log strings
                    len_match = re.match(r'^len\(([^)]+)\)$', var_name)
                    if len_match:
                        inner = len_match.group(1).strip()
                        coll = None
                        if "__self__" in env and isinstance(env["__self__"], dict) and inner in env["__self__"]:
                            coll = env["__self__"][inner]
                        elif inner in env:
                            coll = env[inner]
                        if coll is not None:
                            return str(len(coll))
                        return "0"
                    if "[" in var_name and var_name.endswith("]"):
                        base, idx = var_name[:-1].split("[", 1)
                        base_v = env.get(base)
                        if base_v is None and "__self__" in env and isinstance(env["__self__"], dict):
                            base_v = env["__self__"].get(base)
                        idx_v = idx
                        if idx in env: idx_v = env[idx]
                        elif "__self__" in env and isinstance(env["__self__"], dict) and idx in env["__self__"]:
                            idx_v = env["__self__"][idx]
                        elif idx.isdigit(): idx_v = int(idx)
                        if isinstance(base_v, dict): return str(base_v.get(idx_v, f"{{{var_name}}}"))
                        
                    if "." in var_name:
                        base, prop = var_name.split(".")
                        if base in env and isinstance(env[base], dict):
                            return str(env[base].get(prop, f"{{{var_name}}}"))
                    if "__self__" in env and isinstance(env["__self__"], dict) and var_name in env["__self__"]:
                        return str(env["__self__"][var_name])
                    if var_name in env:
                        return str(env[var_name])
                    return f"{{{var_name}}}"
                msg = re.sub(r'\{([^}]+)\}', repl, msg.strip('"'))
                print(f"    [{level}] {msg}")
                return None
                
            # Built-in: len(collection) -> Int
            if expr.name == "len" and len(args) == 1:
                coll = args[0]
                if coll is None:
                    return 0
                return len(coll)

            # Built-in: del(collection, element_or_key)
            # For lists: removes first element equal to the given value (by identity or equality)
            # For dicts: removes the entry with the given key
            # Returns a sentinel so exec_stmts can write back to the collection
            if expr.name == "del" and len(args) == 2:
                coll = args[0]
                key = args[1]
                if isinstance(coll, list):
                    new_coll = [x for x in coll if x is not key and x != key]
                elif isinstance(coll, dict):
                    new_coll = {k: v for k, v in coll.items() if k != key}
                else:
                    return None
                
                target_expr = expr.args[0]
                if isinstance(target_expr, AtomExpr):
                    return {"__type__": "__del__", "target_type": "atom", "name": target_expr.value, "value": new_coll}
                elif isinstance(target_expr, IndexExpr):
                    idx = self.eval_expr(target_expr.index, env)
                    return {"__type__": "__del__", "target_type": "index", "coll": target_expr.collection, "index": idx, "value": new_coll}
                return None

            if expr.name in self.funcs:
                func = self.funcs[expr.name]
                if getattr(func, 'body', None):
                    local_env = dict(env)
                    for i, param in enumerate(func.params):
                        if i < len(args):
                            param_name = str(param[0])
                            local_env[param_name] = args[i]
                    self.exec_stmts(func.body, local_env)
                    return None

            return {"__type__": "call", "name": expr.name, "args": args}
            
        elif isinstance(expr, BinOp):
            if expr.op == "and": return bool(self.eval_expr(expr.left, env) and self.eval_expr(expr.right, env))
            if expr.op == "or": return bool(self.eval_expr(expr.left, env) or self.eval_expr(expr.right, env))
            left = self.eval_expr(expr.left, env)
            right = self.eval_expr(expr.right, env)
            if expr.op == "==": return left == right
            if expr.op == "!=": return left != right
            if expr.op == "<": return left < right
            if expr.op == ">": return left > right
            if expr.op == "<=": return left <= right
            if expr.op == ">=": return left >= right
            if expr.op == "+":
                if isinstance(left, str) or isinstance(right, str):
                    return str(left if left is not None else "") + str(right if right is not None else "")
                if isinstance(right, list) and left is None:
                    return right
                if isinstance(left, list) and right is None:
                    return left
                if isinstance(left, list) and isinstance(right, list):
                    return left + right
                return left + right
            return False
            
        elif isinstance(expr, ListExpr):
            return [self.eval_expr(e, env) for e in expr.elements]
            
        return None

    def exec_stmts(self, stmts: list, local_env: dict, target_obj: dict = None):
        for stmt in stmts:
            if isinstance(stmt, ReturnStmt):
                return self.eval_expr(stmt.expr, local_env)
            elif isinstance(stmt, Assignment):
                val = self.eval_expr(stmt.expr, local_env)
                if isinstance(stmt.target, IndexExpr):
                    idx = self.eval_expr(stmt.target.index, local_env)
                    coll_name = stmt.target.collection
                    if target_obj and coll_name in target_obj:
                        if not isinstance(target_obj[coll_name], dict): target_obj[coll_name] = {}
                        target_obj[coll_name][idx] = val
                    else:
                        if target_obj is None and "__self__" in local_env and isinstance(local_env["__self__"], dict) and coll_name in local_env["__self__"]:
                            if not isinstance(local_env["__self__"][coll_name], dict): local_env["__self__"][coll_name] = {}
                            local_env["__self__"][coll_name][idx] = val
                        else:
                            if coll_name not in local_env or not isinstance(local_env[coll_name], dict):
                                local_env[coll_name] = {}
                            local_env[coll_name][idx] = val
                else:
                    if target_obj and stmt.target in target_obj:
                        target_obj[stmt.target] = val
                    else:
                        if target_obj is None and "__self__" in local_env and isinstance(local_env["__self__"], dict) and stmt.target in local_env["__self__"]:
                            local_env["__self__"][stmt.target] = val
                        else:
                            local_env[stmt.target] = val
            elif isinstance(stmt, ExprStmt):
                res = self.eval_expr(stmt.expr, local_env)
                if isinstance(res, dict) and res.get("__type__") == "__del__":
                    # Write the updated collection back to wherever it lives
                    target_type = res["target_type"]
                    new_val = res["value"]
                    if target_type == "atom":
                        coll_name = res["name"]
                        if target_obj and coll_name in target_obj:
                            target_obj[coll_name] = new_val
                        elif "__self__" in local_env and isinstance(local_env["__self__"], dict) and coll_name in local_env["__self__"]:
                            local_env["__self__"][coll_name] = new_val
                        else:
                            local_env[coll_name] = new_val
                    elif target_type == "index":
                        coll_name = res["coll"]
                        idx = res["index"]
                        coll = local_env.get(coll_name)
                        if coll is None and "__self__" in local_env and isinstance(local_env["__self__"], dict):
                            coll = local_env["__self__"].get(coll_name)
                        if coll is None:
                            coll = self.config_params.get(coll_name)
                        
                        if isinstance(coll, dict):
                            coll[idx] = new_val
                        elif isinstance(coll, list):
                            coll[idx] = new_val
                elif isinstance(res, dict) and res.get("__type__") == "call":
                    tgt = res.get("args", [None])[0] if res.get("args") else None
                    if isinstance(tgt, dict) and tgt.get("__is_machine__"):
                        self.event_queue.append((tgt, dict(local_env), res))
            elif isinstance(stmt, IfStmt):
                cond = self.eval_expr(stmt.condition, local_env)
                if cond:
                    res = self.exec_stmts(stmt.body, local_env, target_obj)
                    if res is not None:
                        return res
                elif stmt.else_body:
                    res = self.exec_stmts(stmt.else_body, local_env, target_obj)
                    if res is not None:
                        return res
            elif isinstance(stmt, ForStmt):
                iterable = self.eval_expr(stmt.iterable, local_env)
                if hasattr(iterable, '__iter__') and not isinstance(iterable, str):
                    for item in iterable:
                        local_env[stmt.iter_var] = item
                        res = self.exec_stmts(stmt.body, local_env, target_obj)
                        if res is not None:
                            return res
        return None

    def dispatch_event(self, target: dict, env: dict, call_obj: dict):
        if not isinstance(target, dict) or not target.get("__is_machine__"):
            raise InterpreterException("Target is not a machine instance")
            
        mac_name = target["__type__"]
        mac_decl = self.machines[mac_name]
        evt_name = call_obj["name"]
        
        sender_name = "Test"
        if "__self__" in env and isinstance(env["__self__"], dict):
            sender_name = env["__self__"].get("__name__", env["__self__"].get("name", env["__self__"]["__type__"]))
            if isinstance(sender_name, dict): sender_name = "Unknown"
            
        receiver_name = target.get("__name__", target.get("name", target["__type__"]))
        if isinstance(receiver_name, dict): receiver_name = "Unknown"
        
        def format_arg(a):
            if not isinstance(a, dict):
                if isinstance(a, str): return f'"{a}"'
                return str(a)
            if a.get("__is_machine__"):
                return a.get("__name__", a.get("name", a.get("__type__", "Machine")))
            t = a.get("__type__", "Struct")
            parts = []
            for k, v in a.items():
                if not k.startswith("__"):
                    v_str = f'"{v}"' if isinstance(v, str) else str(v)
                    parts.append(f"{k}={v_str}")
            return f"{t}({', '.join(parts)})"
            
        args_strs = [format_arg(a) for a in call_obj.get("args", [])[1:]]
        
        if hasattr(self, 'current_test_trace'):
            self.current_test_trace.append({
                "sender": sender_name,
                "receiver": receiver_name,
                "event": evt_name,
                "args": args_strs
            })
        
        current_state = target.get("state")
        
        # Super simplified matching logic for MVP verification
        for trans in mac_decl.transitions:
            if trans.state_from == current_state and trans.event.name == evt_name:
                
                # Combine global config context with local machine attributes context
                # Extrapolate specific configuration rules matching the current active Machine scoped dynamically
                exec_env = {}
                for k, v in self.config_params.items():
                    if k.startswith(f'{target["__type__"]}.'):
                        local_key = k.split(".", 1)[1]
                        exec_env[local_key] = v
                exec_env.update(target)
                exec_env["__self__"] = target
                
                # Bind event arguments to their corresponding local parameter names based on AST grammar definitions
                # NOTE: call_obj["args"][0] is the target machine name, so event parameters start at index 1
                match_failed = False
                for i, arg in enumerate(trans.event.args):
                    arg_idx = i + 1
                    if arg_idx < len(call_obj["args"]):
                        val = call_obj["args"][arg_idx]
                        if isinstance(arg, tuple):
                            # Param with type: (name, type)
                            name, type_name = arg
                            if isinstance(val, dict) and val.get("__type__") != type_name:
                                match_failed = True
                                break
                            exec_env[name] = val
                        elif hasattr(arg, 'name'):
                            # StructMatch or similar object
                            if not isinstance(val, dict) or val.get("__type__") != arg.name:
                                match_failed = True
                                break
                            # For StructMatch, we also check its fields if any
                            if hasattr(arg, 'fields'):
                                for f in arg.fields:
                                    # f is StructMatchField(name, value)
                                    if f.name not in val or val[f.name] != f.value:
                                        # Simple literal matching for fields
                                        match_failed = True
                                        break
                            if match_failed: break
                            exec_env[arg.name] = val
                        else:
                            # Simple binding or literal string
                            exec_env[str(arg)] = val
                    else:
                        match_failed = True
                        break
                
                if match_failed:
                    continue

                if trans.guard:
                    if not self.eval_expr(trans.guard, exec_env):
                        continue
                
                # Assuming match triggered, jump state
                target["state"] = trans.state_to
                
                # Mutate any fields based on actions explicitly natively
                self.exec_stmts(trans.actions, exec_env, target)
                return True
                
        return False

    def _run_test_stmts(self, stmts: list, env: dict, test_name: str) -> bool:
        for stmt in stmts:
            try:
                if isinstance(stmt, Assignment):
                    if isinstance(stmt.target, IndexExpr):
                        idx = self.eval_expr(stmt.target.index, env)
                        if stmt.target.collection not in env or not isinstance(env[stmt.target.collection], dict):
                            env[stmt.target.collection] = {}
                        val = self.eval_expr(stmt.expr, env)
                        env[stmt.target.collection][idx] = val
                    else:
                        val = self.eval_expr(stmt.expr, env)
                        if isinstance(val, dict) and val.get("__is_machine__"):
                            val["__name__"] = str(stmt.target)
                        env[stmt.target] = val

                elif isinstance(stmt, ExprStmt):
                    res = self.eval_expr(stmt.expr, env)
                    if isinstance(res, dict) and res.get("__type__") == "__del__":
                        target_type = res["target_type"]
                        new_val = res["value"]
                        if target_type == "atom":
                            env[res["name"]] = new_val
                        elif target_type == "index":
                            coll = env.get(res["coll"])
                            if coll is None: coll = self.config_params.get(res["coll"])
                            if isinstance(coll, dict) or isinstance(coll, list):
                                coll[res["index"]] = new_val
                    elif isinstance(res, dict) and res.get("__type__") == "call":
                        target = res.get("args", [None])[0] if res.get("args") else None
                        if isinstance(target, dict) and target.get("__is_machine__"):
                            self.event_queue.append((target, dict(env), res))

                elif isinstance(stmt, AssertStmt):
                    res = self.eval_expr(stmt.expr, env)
                    if not res:
                        print(f"  [FAIL] {test_name}: Assertion failed -> {stmt.expr.left.value if hasattr(stmt.expr, 'left') else stmt.expr}")
                        return False
                        
                elif isinstance(stmt, IfStmt):
                    cond = self.eval_expr(stmt.condition, env)
                    if cond:
                        if not self._run_test_stmts(stmt.body, env, test_name): return False
                    elif stmt.else_body:
                        if not self._run_test_stmts(stmt.else_body, env, test_name): return False
                        
                elif isinstance(stmt, ForStmt):
                    iterable = self.eval_expr(stmt.iterable, env)
                    if hasattr(iterable, '__iter__') and not isinstance(iterable, str):
                        for item in iterable:
                            env[stmt.iter_var] = item
                            if not self._run_test_stmts(stmt.body, env, test_name): return False

                while self.event_queue:
                    queue_tgt, queue_env, queue_event = self.event_queue.pop(0)
                    self.dispatch_event(queue_tgt, queue_env, queue_event)

            except Exception as e:
                print(f"  [ERROR] {test_name}: {e}")
                return False
        return True

    def run_test(self, test: TestDecl):
        env = {}
        self.current_test_nondets = set()
        self.current_test_trace = []
        if not hasattr(self, 'test_traces'):
            self.test_traces = {}
        
        passed = self._run_test_stmts(test.stmts, env, test.name)
        self.test_traces[test.name] = self.current_test_trace
                
        if passed:
            nondet_warn = ""
            if self.current_test_nondets:
                deps = ", ".join(sorted(self.current_test_nondets))
                nondet_warn = f" (WARNING: Test has nondeterministic dependencies: {deps})"
            print(f"  [PASS] {test.name}{nondet_warn}")
            self.tests_passed += 1
        else:
            self.tests_failed += 1
