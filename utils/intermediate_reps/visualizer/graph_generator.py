import graphviz
from parser.ast_nodes import Program, MachineDecl, TransitionDecl, Assignment, ExprStmt, CallExpr

def format_action(action) -> str:
    if isinstance(action, Assignment):
        return f"{action.target} = ..."
    elif isinstance(action, ExprStmt):
        expr = action.expr
        if isinstance(expr, CallExpr):
            return f"{expr.name}(...)"
    return "..."

def format_transition_label(t: TransitionDecl) -> str:
    # Build transition label: event [guard] / actions
    args_str = ", ".join(str(a) for a in t.event.args)
    event_str = f"{t.event.name}({args_str})"
    guard_str = f" [guard]" if t.guard else "" # Simplified
    
    action_strs = [format_action(a) for a in t.actions]
    actions_joined = "\\n".join(action_strs)
    
    if actions_joined:
        return f"{event_str}{guard_str}\\n{actions_joined}"
    return f"{event_str}{guard_str}"

def generate_machine_graph(machine: MachineDecl) -> graphviz.Digraph:
    dot = graphviz.Digraph(name=machine.name)
    dot.attr(rankdir='LR')
    dot.attr('node', style='filled', color='lightblue2', fontname="Helvetica")
    dot.attr('edge', fontname="Helvetica", fontsize="10")
    
    # State Nodes
    dot.node('start', shape='point')
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
