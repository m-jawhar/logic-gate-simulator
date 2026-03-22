"""
GUI Module - Visual interface for the Logic Gate Simulator
Uses Tkinter for cross-platform compatibility
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional, Tuple
from gates import (
    Gate,
    AndGate,
    OrGate,
    NotGate,
    NandGate,
    NorGate,
    XorGate,
    InputNode,
    OutputNode,
    Wire,
)
from simulation import Circuit, SimulationEngine, format_truth_table


class LogicGateSimulator:
    """Main application class for the Logic Gate Simulator"""

    # Color scheme
    COLORS = {
        "bg": "#1e1e2e",
        "canvas_bg": "#181825",
        "gate_fill": "#45475a",
        "gate_outline": "#89b4fa",
        "gate_text": "#cdd6f4",
        "input_on": "#a6e3a1",
        "input_off": "#f38ba8",
        "output_on": "#a6e3a1",
        "output_off": "#f38ba8",
        "wire": "#89b4fa",
        "wire_on": "#a6e3a1",
        "wire_off": "#6c7086",
        "selected": "#f9e2af",
        "connector": "#cba6f7",
        "panel_bg": "#313244",
        "button_bg": "#45475a",
        "button_fg": "#cdd6f4",
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Visual Logic Gate Simulator")
        self.root.geometry("1200x800")
        self.root.configure(bg=self.COLORS["bg"])

        # Circuit and simulation
        self.circuit = Circuit()
        self.engine = SimulationEngine(self.circuit)

        # Interaction state
        self.selected_item = None
        self.dragging = False
        self.drag_offset = (0, 0)
        self.wiring_mode = False
        self.wire_start = None
        self.wire_start_type = None
        self.temp_wire_id = None

        # Counters for naming
        self.input_counter = 0
        self.output_counter = 0
        self.gate_counter = 0

        self._setup_ui()
        self._bind_events()

    def _setup_ui(self):
        """Setup the user interface"""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel - Toolbox
        self._setup_toolbox(main_frame)

        # Center - Canvas
        self._setup_canvas(main_frame)

        # Right panel - Properties and Truth Table
        self._setup_right_panel(main_frame)

        # Status bar
        self.status_var = tk.StringVar(
            value="Ready - Drag components to canvas, click to select, wire mode to connect"
        )
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, relief=tk.SUNKEN
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _setup_toolbox(self, parent):
        """Setup the toolbox panel"""
        toolbox = ttk.LabelFrame(parent, text="Components", padding=10)
        toolbox.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Style for buttons
        style = ttk.Style()
        style.configure("Tool.TButton", padding=10)

        # Input/Output section
        ttk.Label(toolbox, text="I/O Nodes", font=("Arial", 10, "bold")).pack(
            pady=(0, 5)
        )

        ttk.Button(
            toolbox,
            text="➕ Input",
            style="Tool.TButton",
            command=lambda: self._add_component("input"),
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="📤 Output",
            style="Tool.TButton",
            command=lambda: self._add_component("output"),
        ).pack(fill=tk.X, pady=2)

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Gates section
        ttk.Label(toolbox, text="Logic Gates", font=("Arial", 10, "bold")).pack(
            pady=(0, 5)
        )

        gate_types = [
            ("AND Gate", "and"),
            ("OR Gate", "or"),
            ("NOT Gate", "not"),
            ("NAND Gate", "nand"),
            ("NOR Gate", "nor"),
            ("XOR Gate", "xor"),
        ]

        for label, gate_type in gate_types:
            ttk.Button(
                toolbox,
                text=label,
                style="Tool.TButton",
                command=lambda gt=gate_type: self._add_component(gt),
            ).pack(fill=tk.X, pady=2)

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Actions section
        ttk.Label(toolbox, text="Actions", font=("Arial", 10, "bold")).pack(pady=(0, 5))

        self.wire_btn = ttk.Button(
            toolbox,
            text="🔗 Wire Mode: OFF",
            style="Tool.TButton",
            command=self._toggle_wire_mode,
        )
        self.wire_btn.pack(fill=tk.X, pady=2)

        ttk.Button(
            toolbox,
            text="🗑️ Delete Selected",
            style="Tool.TButton",
            command=self._delete_selected,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="🔄 Clear Circuit",
            style="Tool.TButton",
            command=self._clear_circuit,
        ).pack(fill=tk.X, pady=2)

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Button(
            toolbox,
            text="▶️ Simulate",
            style="Tool.TButton",
            command=self._run_simulation,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="📊 Truth Table",
            style="Tool.TButton",
            command=self._show_truth_table,
        ).pack(fill=tk.X, pady=2)

    def _setup_canvas(self, parent):
        """Setup the main canvas area"""
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        # Canvas with scrollbars
        self.canvas = tk.Canvas(
            canvas_frame,
            bg=self.COLORS["canvas_bg"],
            highlightthickness=2,
            highlightbackground=self.COLORS["gate_outline"],
        )

        h_scroll = ttk.Scrollbar(
            canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview
        )
        v_scroll = ttk.Scrollbar(
            canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview
        )

        self.canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        self.canvas.configure(scrollregion=(0, 0, 2000, 2000))

        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Draw grid
        self._draw_grid()

    def _draw_grid(self):
        """Draw a subtle grid on the canvas"""
        grid_spacing = 20
        for i in range(0, 2000, grid_spacing):
            self.canvas.create_line(i, 0, i, 2000, fill="#313244", tags="grid")
            self.canvas.create_line(0, i, 2000, i, fill="#313244", tags="grid")
        self.canvas.tag_lower("grid")

    def _setup_right_panel(self, parent):
        """Setup the right panel with properties and truth table"""
        right_panel = ttk.Frame(parent, width=300)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        right_panel.pack_propagate(False)

        # Properties section
        props_frame = ttk.LabelFrame(right_panel, text="Properties", padding=10)
        props_frame.pack(fill=tk.X, pady=5)

        self.props_text = tk.Text(
            props_frame,
            height=8,
            width=35,
            bg=self.COLORS["panel_bg"],
            fg=self.COLORS["gate_text"],
            font=("Consolas", 10),
        )
        self.props_text.pack(fill=tk.X)
        self.props_text.insert("1.0", "Select a component to view properties")
        self.props_text.config(state=tk.DISABLED)

        # Boolean Expression section
        expr_frame = ttk.LabelFrame(right_panel, text="Boolean Expression", padding=10)
        expr_frame.pack(fill=tk.X, pady=5)

        self.expr_text = tk.Text(
            expr_frame,
            height=5,
            width=35,
            bg=self.COLORS["panel_bg"],
            fg=self.COLORS["gate_text"],
            font=("Consolas", 10),
            wrap=tk.WORD,
        )
        self.expr_text.pack(fill=tk.X)

        # Truth Table section
        table_frame = ttk.LabelFrame(right_panel, text="Truth Table", padding=10)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.table_text = scrolledtext.ScrolledText(
            table_frame,
            width=35,
            bg=self.COLORS["panel_bg"],
            fg=self.COLORS["gate_text"],
            font=("Consolas", 10),
        )
        self.table_text.pack(fill=tk.BOTH, expand=True)

    def _bind_events(self):
        """Bind mouse and keyboard events"""
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.root.bind("<Delete>", lambda e: self._delete_selected())
        self.root.bind("<Escape>", lambda e: self._cancel_wiring())

    def _add_component(self, component_type: str):
        """Add a new component to the circuit"""
        x, y = 100, 100 + len(self.circuit.get_all_components()) * 80

        if component_type == "input":
            self.input_counter += 1
            node = InputNode(f"IN{self.input_counter}")
            node.move_to(x, y)
            self.circuit.add_input(node)
            self._draw_input_node(node)

        elif component_type == "output":
            self.output_counter += 1
            node = OutputNode(f"OUT{self.output_counter}")
            node.move_to(x + 400, y)
            self.circuit.add_output(node)
            self._draw_output_node(node)

        else:
            self.gate_counter += 1
            gate_classes = {
                "and": AndGate,
                "or": OrGate,
                "not": NotGate,
                "nand": NandGate,
                "nor": NorGate,
                "xor": XorGate,
            }
            gate = gate_classes[component_type](
                f"{component_type.upper()}{self.gate_counter}"
            )
            gate.move_to(x + 150, y)
            self.circuit.add_gate(gate)
            self._draw_gate(gate)

        self._run_simulation()

    def _draw_gate(self, gate: Gate):
        """Draw a gate on the canvas"""
        x, y = gate.x, gate.y
        w, h = gate.width, gate.height

        # Gate body
        fill_color = (
            self.COLORS["selected"] if gate.selected else self.COLORS["gate_fill"]
        )
        gate.canvas_id = self.canvas.create_rectangle(
            x,
            y,
            x + w,
            y + h,
            fill=fill_color,
            outline=self.COLORS["gate_outline"],
            width=2,
            tags=("gate", f"gate_{id(gate)}"),
        )

        # Gate symbol
        self.canvas.create_text(
            x + w / 2,
            y + h / 2,
            text=gate.get_symbol(),
            fill=self.COLORS["gate_text"],
            font=("Arial", 12, "bold"),
            tags=("gate", f"gate_{id(gate)}"),
        )

        # Input connectors
        for i in range(gate.num_inputs):
            ix, iy = gate.get_input_position(i)
            self.canvas.create_oval(
                ix - 6,
                iy - 6,
                ix + 6,
                iy + 6,
                fill=self.COLORS["connector"],
                outline="white",
                tags=("connector", "input_connector", f"gate_{id(gate)}"),
            )
            # Input label
            self.canvas.create_text(
                ix + 15,
                iy,
                text=f"I{i}",
                fill=self.COLORS["gate_text"],
                font=("Arial", 8),
                tags=("gate", f"gate_{id(gate)}"),
            )

        # Output connector
        ox, oy = gate.get_output_position()
        output_color = (
            self.COLORS["output_on"] if gate.get_output() else self.COLORS["output_off"]
        )
        if gate.get_output() is None:
            output_color = self.COLORS["connector"]

        self.canvas.create_oval(
            ox - 6,
            oy - 6,
            ox + 6,
            oy + 6,
            fill=output_color,
            outline="white",
            tags=("connector", "output_connector", f"gate_{id(gate)}"),
        )

        # Output value
        output_text = (
            "?" if gate.get_output() is None else ("1" if gate.get_output() else "0")
        )
        self.canvas.create_text(
            ox + 15,
            oy,
            text=output_text,
            fill=self.COLORS["gate_text"],
            font=("Arial", 10, "bold"),
            tags=("gate", f"gate_{id(gate)}"),
        )

    def _draw_input_node(self, node: InputNode):
        """Draw an input node on the canvas"""
        x, y = node.x, node.y
        w, h = node.width, node.height

        fill_color = self.COLORS["input_on"] if node.value else self.COLORS["input_off"]
        if node.selected:
            outline_color = self.COLORS["selected"]
        else:
            outline_color = self.COLORS["gate_outline"]

        node.canvas_id = self.canvas.create_rectangle(
            x,
            y,
            x + w,
            y + h,
            fill=fill_color,
            outline=outline_color,
            width=2,
            tags=("input_node", f"input_{id(node)}"),
        )

        # Name and value
        self.canvas.create_text(
            x + w / 2,
            y + h / 3,
            text=node.name,
            fill="black",
            font=("Arial", 9, "bold"),
            tags=("input_node", f"input_{id(node)}"),
        )
        self.canvas.create_text(
            x + w / 2,
            y + 2 * h / 3,
            text="1" if node.value else "0",
            fill="black",
            font=("Arial", 14, "bold"),
            tags=("input_node", f"input_{id(node)}"),
        )

        # Output connector
        ox, oy = node.get_output_position()
        self.canvas.create_oval(
            ox - 6,
            oy - 6,
            ox + 6,
            oy + 6,
            fill=self.COLORS["connector"],
            outline="white",
            tags=("connector", "output_connector", f"input_{id(node)}"),
        )

    def _draw_output_node(self, node: OutputNode):
        """Draw an output node on the canvas"""
        x, y = node.x, node.y
        w, h = node.width, node.height

        if node.value is None:
            fill_color = self.COLORS["gate_fill"]
        else:
            fill_color = (
                self.COLORS["output_on"] if node.value else self.COLORS["output_off"]
            )

        if node.selected:
            outline_color = self.COLORS["selected"]
        else:
            outline_color = self.COLORS["gate_outline"]

        node.canvas_id = self.canvas.create_rectangle(
            x,
            y,
            x + w,
            y + h,
            fill=fill_color,
            outline=outline_color,
            width=2,
            tags=("output_node", f"output_{id(node)}"),
        )

        # Name and value
        self.canvas.create_text(
            x + w / 2,
            y + h / 3,
            text=node.name,
            fill=self.COLORS["gate_text"] if node.value is None else "black",
            font=("Arial", 9, "bold"),
            tags=("output_node", f"output_{id(node)}"),
        )

        value_text = "?" if node.value is None else ("1" if node.value else "0")
        self.canvas.create_text(
            x + w / 2,
            y + 2 * h / 3,
            text=value_text,
            fill=self.COLORS["gate_text"] if node.value is None else "black",
            font=("Arial", 14, "bold"),
            tags=("output_node", f"output_{id(node)}"),
        )

        # Input connector
        ix, iy = node.get_input_position()
        self.canvas.create_oval(
            ix - 6,
            iy - 6,
            ix + 6,
            iy + 6,
            fill=self.COLORS["connector"],
            outline="white",
            tags=("connector", "input_connector", f"output_{id(node)}"),
        )

    def _draw_wire(self, wire: Wire):
        """Draw a wire connection"""
        start = wire.get_start_pos()
        end = wire.get_end_pos()

        # Determine wire color based on value
        value = wire.get_value()
        if value is None:
            color = self.COLORS["wire"]
        elif value:
            color = self.COLORS["wire_on"]
        else:
            color = self.COLORS["wire_off"]

        # Draw curved wire
        mid_x = (start[0] + end[0]) / 2

        wire.canvas_id = self.canvas.create_line(
            start[0],
            start[1],
            mid_x,
            start[1],
            mid_x,
            end[1],
            end[0],
            end[1],
            fill=color,
            width=3,
            smooth=True,
            tags=("wire", f"wire_{id(wire)}"),
        )
        self.canvas.tag_lower("wire")
        self.canvas.tag_lower("grid")

    def _redraw_all(self):
        """Redraw all components"""
        # Clear canvas except grid
        self.canvas.delete("gate", "input_node", "output_node", "wire", "connector")

        # Draw wires first (behind)
        for wire in self.circuit.wires:
            self._draw_wire(wire)

        # Draw gates
        for gate in self.circuit.gates:
            self._draw_gate(gate)

        # Draw input nodes
        for node in self.circuit.input_nodes:
            self._draw_input_node(node)

        # Draw output nodes
        for node in self.circuit.output_nodes:
            self._draw_output_node(node)

    def _find_component_at(self, x: int, y: int):
        """Find component at given coordinates"""
        for gate in self.circuit.gates:
            if gate.contains_point(x, y):
                return gate, "gate"

        for node in self.circuit.input_nodes:
            if node.contains_point(x, y):
                return node, "input"

        for node in self.circuit.output_nodes:
            if node.contains_point(x, y):
                return node, "output"

        return None, None

    def _find_connector_at(self, x: int, y: int) -> Tuple[Optional[object], str, int]:
        """Find connector at coordinates. Returns (component, type, index)"""
        tolerance = 10

        # Check gate connectors
        for gate in self.circuit.gates:
            # Check output connector
            ox, oy = gate.get_output_position()
            if abs(x - ox) < tolerance and abs(y - oy) < tolerance:
                return gate, "gate_output", 0

            # Check input connectors
            for i in range(gate.num_inputs):
                ix, iy = gate.get_input_position(i)
                if abs(x - ix) < tolerance and abs(y - iy) < tolerance:
                    return gate, "gate_input", i

        # Check input node connectors
        for node in self.circuit.input_nodes:
            ox, oy = node.get_output_position()
            if abs(x - ox) < tolerance and abs(y - oy) < tolerance:
                return node, "input_output", 0

        # Check output node connectors
        for node in self.circuit.output_nodes:
            ix, iy = node.get_input_position()
            if abs(x - ix) < tolerance and abs(y - iy) < tolerance:
                return node, "output_input", 0

        return None, "", 0

    def _on_canvas_click(self, event):
        """Handle canvas click"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        if self.wiring_mode:
            self._handle_wiring_click(x, y)
            return

        # Find clicked component
        component, comp_type = self._find_component_at(x, y)

        # Deselect previous
        if self.selected_item:
            self.selected_item.selected = False

        if component:
            component.selected = True
            self.selected_item = component
            self.dragging = True
            self.drag_offset = (x - component.x, y - component.y)
            self._update_properties(component, comp_type)
        else:
            self.selected_item = None
            self._clear_properties()

        self._redraw_all()

    def _handle_wiring_click(self, x: int, y: int):
        """Handle click in wiring mode"""
        component, conn_type, index = self._find_connector_at(x, y)

        if component is None:
            self.status_var.set("Click on a connector to start/end wire")
            return

        if self.wire_start is None:
            # Start wiring - must be an output connector
            if conn_type in ("gate_output", "input_output"):
                self.wire_start = component
                self.wire_start_type = conn_type
                self.status_var.set(
                    f"Wiring from {getattr(component, 'name', 'component')} - click on an input connector"
                )
            else:
                self.status_var.set("Start wire from an OUTPUT connector")
        else:
            # End wiring - must be an input connector
            if conn_type in ("gate_input", "output_input"):
                # Create wire
                if self.wire_start_type == "input_output":
                    source_type = "input"
                else:
                    source_type = "gate"

                if conn_type == "output_input":
                    target_type = "output"
                else:
                    target_type = "gate"

                wire = Wire(self.wire_start, source_type, component, target_type, index)
                self.circuit.add_wire(wire)

                self.status_var.set(f"Wire connected!")
                self._run_simulation()
            else:
                self.status_var.set("End wire on an INPUT connector")

            # Reset wiring state
            self.wire_start = None
            self.wire_start_type = None
            if self.temp_wire_id:
                self.canvas.delete(self.temp_wire_id)
                self.temp_wire_id = None

        self._redraw_all()

    def _on_canvas_drag(self, event):
        """Handle canvas drag"""
        if not self.dragging or not self.selected_item or self.wiring_mode:
            return

        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        new_x = x - self.drag_offset[0]
        new_y = y - self.drag_offset[1]

        self.selected_item.move_to(new_x, new_y)
        self._redraw_all()

    def _on_canvas_release(self, event):
        """Handle canvas release"""
        self.dragging = False

    def _on_double_click(self, event):
        """Handle double click - toggle input nodes"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        component, comp_type = self._find_component_at(x, y)

        if comp_type == "input" and isinstance(component, InputNode):
            component.toggle()
            self._run_simulation()
            self._redraw_all()

    def _on_mouse_move(self, event):
        """Handle mouse movement for wire preview"""
        if not self.wiring_mode or self.wire_start is None:
            return

        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        # Draw temporary wire
        if self.temp_wire_id:
            self.canvas.delete(self.temp_wire_id)

        start = self.wire_start.get_output_position()
        mid_x = (start[0] + x) / 2

        self.temp_wire_id = self.canvas.create_line(
            start[0],
            start[1],
            mid_x,
            start[1],
            mid_x,
            y,
            x,
            y,
            fill=self.COLORS["wire"],
            width=2,
            dash=(5, 3),
            smooth=True,
        )

    def _toggle_wire_mode(self):
        """Toggle wiring mode"""
        self.wiring_mode = not self.wiring_mode
        if self.wiring_mode:
            self.wire_btn.configure(text="🔗 Wire Mode: ON")
            self.status_var.set(
                "WIRE MODE - Click output connector, then input connector"
            )
            self.canvas.configure(cursor="crosshair")
        else:
            self.wire_btn.configure(text="🔗 Wire Mode: OFF")
            self.status_var.set("Ready")
            self.canvas.configure(cursor="")
            self._cancel_wiring()

    def _cancel_wiring(self):
        """Cancel current wiring operation"""
        self.wire_start = None
        self.wire_start_type = None
        if self.temp_wire_id:
            self.canvas.delete(self.temp_wire_id)
            self.temp_wire_id = None

    def _delete_selected(self):
        """Delete the selected component"""
        if not self.selected_item:
            return

        if isinstance(self.selected_item, Gate):
            self.circuit.remove_gate(self.selected_item)
        elif isinstance(self.selected_item, InputNode):
            self.circuit.remove_input(self.selected_item)
        elif isinstance(self.selected_item, OutputNode):
            self.circuit.remove_output(self.selected_item)

        self.selected_item = None
        self._clear_properties()
        self._run_simulation()
        self._redraw_all()

    def _clear_circuit(self):
        """Clear the entire circuit"""
        if messagebox.askyesno(
            "Clear Circuit", "Are you sure you want to clear the entire circuit?"
        ):
            self.circuit.clear()
            self.selected_item = None
            self.input_counter = 0
            self.output_counter = 0
            self.gate_counter = 0
            self._clear_properties()
            self._redraw_all()
            self.table_text.delete("1.0", tk.END)
            self.expr_text.delete("1.0", tk.END)

    def _run_simulation(self):
        """Run the simulation"""
        self.engine.simulate()
        self._redraw_all()
        self._update_truth_table()
        self._update_expression()

    def _show_truth_table(self):
        """Show truth table in a popup window"""
        input_names, output_names, rows = self.engine.generate_truth_table()
        table_str = format_truth_table(input_names, output_names, rows)

        # Create popup window
        popup = tk.Toplevel(self.root)
        popup.title("Truth Table")
        popup.geometry("400x500")
        popup.configure(bg=self.COLORS["bg"])

        text = scrolledtext.ScrolledText(
            popup,
            font=("Consolas", 12),
            bg=self.COLORS["panel_bg"],
            fg=self.COLORS["gate_text"],
        )
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert("1.0", table_str)
        text.config(state=tk.DISABLED)

    def _update_truth_table(self):
        """Update the truth table display"""
        input_names, output_names, rows = self.engine.generate_truth_table()
        table_str = format_truth_table(input_names, output_names, rows)

        self.table_text.delete("1.0", tk.END)
        self.table_text.insert("1.0", table_str)

    def _update_expression(self):
        """Update the Boolean expression display"""
        expressions = self.engine.get_boolean_expression()

        self.expr_text.delete("1.0", tk.END)
        if expressions:
            for out_name, expr in expressions.items():
                self.expr_text.insert(tk.END, f"{out_name} = {expr}\n\n")
        else:
            self.expr_text.insert("1.0", "Add inputs and outputs to see expression")

    def _update_properties(self, component, comp_type: str):
        """Update the properties panel"""
        self.props_text.config(state=tk.NORMAL)
        self.props_text.delete("1.0", tk.END)

        if comp_type == "gate":
            props = f"""Gate: {component.get_symbol()}
Name: {component.name}
Inputs: {component.num_inputs}
Input Values: {component.inputs}
Output: {component.get_output()}
Position: ({component.x}, {component.y})
"""
        elif comp_type == "input":
            props = f"""Input Node
Name: {component.name}
Value: {component.value} ({'HIGH' if component.value else 'LOW'})
Position: ({component.x}, {component.y})

Double-click to toggle!
"""
        elif comp_type == "output":
            props = f"""Output Node
Name: {component.name}
Value: {component.value}
Position: ({component.x}, {component.y})
"""
        else:
            props = "Unknown component"

        self.props_text.insert("1.0", props)
        self.props_text.config(state=tk.DISABLED)

    def _clear_properties(self):
        """Clear the properties panel"""
        self.props_text.config(state=tk.NORMAL)
        self.props_text.delete("1.0", tk.END)
        self.props_text.insert("1.0", "Select a component to view properties")
        self.props_text.config(state=tk.DISABLED)


def main():
    root = tk.Tk()
    app = LogicGateSimulator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
