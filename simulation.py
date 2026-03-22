"""
Simulation Engine - Handles circuit simulation and truth table generation
"""

from typing import List, Dict, Optional, Tuple
from itertools import product
from gates import Gate, InputNode, OutputNode, Wire


class Circuit:
    """Represents a complete logic circuit"""

    def __init__(self):
        self.gates: List[Gate] = []
        self.input_nodes: List[InputNode] = []
        self.output_nodes: List[OutputNode] = []
        self.wires: List[Wire] = []

    def add_gate(self, gate: Gate) -> None:
        self.gates.append(gate)

    def remove_gate(self, gate: Gate) -> None:
        # Remove associated wires first
        self.wires = [w for w in self.wires if w.source != gate and w.target != gate]
        self.gates.remove(gate)

    def add_input(self, input_node: InputNode) -> None:
        self.input_nodes.append(input_node)

    def remove_input(self, input_node: InputNode) -> None:
        self.wires = [w for w in self.wires if w.source != input_node]
        self.input_nodes.remove(input_node)

    def add_output(self, output_node: OutputNode) -> None:
        self.output_nodes.append(output_node)

    def remove_output(self, output_node: OutputNode) -> None:
        self.wires = [w for w in self.wires if w.target != output_node]
        self.output_nodes.remove(output_node)

    def add_wire(self, wire: Wire) -> None:
        self.wires.append(wire)

    def remove_wire(self, wire: Wire) -> None:
        self.wires.remove(wire)

    def clear(self) -> None:
        """Clear the entire circuit"""
        self.gates.clear()
        self.input_nodes.clear()
        self.output_nodes.clear()
        self.wires.clear()

    def get_all_components(self):
        """Get all components in the circuit"""
        return self.gates + self.input_nodes + self.output_nodes


class SimulationEngine:
    """Handles the simulation of logic circuits"""

    def __init__(self, circuit: Circuit):
        self.circuit = circuit

    def simulate(self) -> None:
        """
        Run simulation to propagate values through the circuit.
        Uses topological sorting to ensure proper evaluation order.
        """
        # Reset all gate inputs
        for gate in self.circuit.gates:
            gate.inputs = [None] * gate.num_inputs

        # Reset output nodes
        for output in self.circuit.output_nodes:
            output.value = None

        # Build dependency graph and propagate values
        evaluated = set()
        max_iterations = len(self.circuit.gates) + len(self.circuit.output_nodes) + 1

        for _ in range(max_iterations):
            progress = False

            # Process wires from input nodes first
            for wire in self.circuit.wires:
                if wire.source_type == "input":
                    value = wire.source.get_output()
                    if wire.target_type == "gate":
                        wire.target.set_input(wire.target_input_index, value)
                    elif wire.target_type == "output":
                        wire.target.set_value(value)

            # Process wires from gates
            for wire in self.circuit.wires:
                if wire.source_type == "gate":
                    source_output = wire.source.get_output()
                    if source_output is not None:
                        if wire.target_type == "gate":
                            wire.target.set_input(
                                wire.target_input_index, source_output
                            )
                            progress = True
                        elif wire.target_type == "output":
                            wire.target.set_value(source_output)
                            progress = True

            # Check if all gates are evaluated
            all_evaluated = all(
                gate.get_output() is not None
                for gate in self.circuit.gates
                if self._has_all_inputs_connected(gate)
            )
            if all_evaluated and not progress:
                break

    def _has_all_inputs_connected(self, gate: Gate) -> bool:
        """Check if all inputs of a gate are connected"""
        connected_inputs = 0
        for wire in self.circuit.wires:
            if wire.target == gate:
                connected_inputs += 1
        return connected_inputs == gate.num_inputs

    def generate_truth_table(self) -> Tuple[List[str], List[str], List[List[bool]]]:
        """
        Generate truth table for the current circuit.
        Returns: (input_names, output_names, rows)
        """
        if not self.circuit.input_nodes or not self.circuit.output_nodes:
            return [], [], []

        input_names = [inp.name for inp in self.circuit.input_nodes]
        output_names = [out.name for out in self.circuit.output_nodes]

        # Save current input states
        original_states = [inp.value for inp in self.circuit.input_nodes]

        rows = []
        num_inputs = len(self.circuit.input_nodes)

        # Generate all possible input combinations
        for combination in product([False, True], repeat=num_inputs):
            # Set inputs
            for i, value in enumerate(combination):
                self.circuit.input_nodes[i].value = value

            # Simulate
            self.simulate()

            # Record row
            row = list(combination) + [out.value for out in self.circuit.output_nodes]
            rows.append(row)

        # Restore original states
        for i, state in enumerate(original_states):
            self.circuit.input_nodes[i].value = state

        # Re-simulate with original values
        self.simulate()

        return input_names, output_names, rows

    def get_boolean_expression(self) -> Dict[str, str]:
        """
        Generate Boolean expression for each output (Sum of Products form).
        Returns a dict mapping output names to their Boolean expressions.
        """
        input_names, output_names, rows = self.generate_truth_table()

        if not rows:
            return {}

        expressions = {}
        num_inputs = len(input_names)

        for out_idx, out_name in enumerate(output_names):
            terms = []

            for row in rows:
                # Check if output is True for this row
                output_value = row[num_inputs + out_idx]
                if output_value:
                    # Build minterm
                    term_parts = []
                    for i, inp_name in enumerate(input_names):
                        if row[i]:
                            term_parts.append(inp_name)
                        else:
                            term_parts.append(f"¬{inp_name}")

                    if term_parts:
                        terms.append("(" + " ∧ ".join(term_parts) + ")")

            if terms:
                expressions[out_name] = " ∨ ".join(terms)
            else:
                expressions[out_name] = "0 (Always False)"

        return expressions


def format_truth_table(
    input_names: List[str], output_names: List[str], rows: List[List[bool]]
) -> str:
    """Format truth table as a string for display"""
    if not rows:
        return "No truth table available (add inputs and outputs)"

    all_names = input_names + output_names
    col_widths = [max(len(name), 5) for name in all_names]

    # Header
    header = " | ".join(
        name.center(width) for name, width in zip(all_names, col_widths)
    )
    separator = "-+-".join("-" * width for width in col_widths)

    # Rows
    row_strs = []
    for row in rows:
        values = ["1" if v else "0" for v in row]
        row_str = " | ".join(
            val.center(width) for val, width in zip(values, col_widths)
        )
        row_strs.append(row_str)

    return "\n".join([header, separator] + row_strs)
