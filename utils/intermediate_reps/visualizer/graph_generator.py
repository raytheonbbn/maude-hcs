import graphviz
import html
from parser.ast_nodes import (
    Program, MachineDecl, TransitionDecl, Assignment, ExprStmt,
    CallExpr, AtomExpr, BinOp, IndexExpr, IfStmt, ForStmt, ListExpr, StructInitExpr
)

def expr_to_str(expr) -> str:
    if isinstance(expr, AtomExpr):
        if isinstance(expr.value, str) and not expr.value.startswith('"'):
            # Just print the variable
            return expr.value
        return str(expr.value)
    elif isinstance(expr, BinOp):
        return f"{expr_to_str(expr.left)} {expr.op} {expr_to_str(expr.right)}"
    elif isinstance(expr, CallExpr):
        args = ", ".join(expr_to_str(a) for a in expr.args)
        return f"{expr.name}({args})"
    elif isinstance(expr, IndexExpr):
        return f"{expr.collection}[{expr_to_str(expr.index)}]"
    elif isinstance(expr, ListExpr):
        elements = ", ".join(expr_to_str(e) for e in expr.elements)
        return f"[{elements}]"
    elif isinstance(expr, StructInitExpr):
        args = ", ".join(expr_to_str(a) for a in expr.args)
        return f"{expr.struct_name}({args})"
    return "..."

def format_action(action) -> str:
    if isinstance(action, Assignment):
        target = expr_to_str(action.target) if isinstance(action.target, IndexExpr) else action.target
        return f"{target} = {expr_to_str(action.expr)}"
    elif isinstance(action, ExprStmt):
        return expr_to_str(action.expr)
    elif isinstance(action, IfStmt):
        return f"if {expr_to_str(action.condition)} {{ ... }}"
    elif isinstance(action, ForStmt):
        return f"for {action.iter_var} in {expr_to_str(action.iterable)} {{ ... }}"
    return "..."

def format_transition_label(t: TransitionDecl) -> str:
    args_str = ", ".join(str(a) for a in t.event.args)
    event_str = f"{t.event.name}({args_str})"
    guard_str = f" [{expr_to_str(t.guard)}]" if t.guard else ""
    
    action_strs = [html.escape(format_action(a)) for a in t.actions]
    actions_joined = "<BR/>".join(action_strs)
    
    # Using HTML-like labels for Mealy Machine presentation
    html_label = f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">'
    html_label += f'<TR><TD BORDER="0"><B>{html.escape(event_str)}{html.escape(guard_str)}</B></TD></TR>'
    if actions_joined:
        html_label += f'<TR><TD BORDER="0" ALIGN="LEFT"><FONT COLOR="blue">{actions_joined}</FONT></TD></TR>'
    html_label += '</TABLE>>'
    
    return html_label

def generate_machine_graph(machine: MachineDecl) -> graphviz.Digraph:
    dot = graphviz.Digraph(name=machine.name)
    dot.attr(rankdir='LR')
    dot.attr('node', style='filled', color='lightblue2', fontname="Helvetica", shape='ellipse')
    dot.attr('edge', fontname="Helvetica", fontsize="10")
    
    # State Nodes
    dot.node('start', shape='point', width='0.2')
    
    for state in machine.states:
        shape = 'doublecircle' if state == machine.initial_state else 'circle'
        dot.node(state, state, shape=shape)
    
    if machine.initial_state:
        dot.edge('start', machine.initial_state)

    # Transitions
    for t in machine.transitions:
        label = format_transition_label(t)
        dot.edge(t.state_from, t.state_to, label=label)
        
    return dot

def generate_graphs(prog: Program) -> list[graphviz.Digraph]:
    return [generate_machine_graph(m) for m in prog.machines]

def generate_sequence_mermaid(test_name: str, trace: list) -> str:
    lines = ["```mermaid", "sequenceDiagram", f"  %% Sequence for test: {test_name}"]
    participants = []
    
    for t in trace:
        s = t["sender"]
        r = t["receiver"]
        if s not in participants:
            participants.append(s)
            lines.insert(3, f"  participant {s}")
        if r not in participants:
            participants.append(r)
            lines.insert(3, f"  participant {r}")
            
    for t in trace:
        s = t["sender"]
        r = t["receiver"]
        evt = t["event"]
        args = ", ".join(t.get("args", []))
        
        # Mermaid sequence parsers aggressively drop anything following a literal ASCII hashtag `#`
        # Using fullwidth unicode alternative allows visual parity without breaking sequence labels
        args = args.replace("#", "＃").replace("&#35;", "＃")
        
        if args:
            lines.append(f"  {s}->>{r}: {evt}({args})")
        else:
            lines.append(f"  {s}->>{r}: {evt}()")
            
    lines.append("```")
    return "\n".join(lines)


def generate_sequence_graphviz(test_name: str, trace: list) -> graphviz.Digraph:
    dot = graphviz.Digraph(name=f"Sequence_{test_name.replace(' ', '_')}")
    dot.attr(rankdir='TB')
    dot.attr('node', style='filled', color='lightyellow', fontname="Helvetica", shape='box')
    dot.attr('edge', fontname="Helvetica", fontsize="10")
    
    # We create an explicit chronological timeline constraint using invis edges 
    # to force vertical order.
    
    for i, t in enumerate(trace):
        s = t["sender"]
        r = t["receiver"]
        evt = t["event"]
        args = ", ".join(t.get("args", []))
        label = f"({i+1}) {evt}\\n{args}"
        
        dot.edge(s, r, label=label, constraint="false")
        
        # Link a hidden chronological spine to force vertical rendering sequence
        if i > 0:
            prev_s = trace[i-1]["sender"]
            dot.edge(prev_s, s, style="invis", weight="10")
            
    return dot

