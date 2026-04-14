"""
GUI Module - Visual interface for the Logic Gate Simulator
Uses Tkinter for cross-platform compatibility
"""

import json
import os
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk
from typing import Literal, Optional, Tuple, Union
from urllib.parse import parse_qs, quote, urlparse

from gates import (
    AndGate,
    Gate,
    InputNode,
    NandGate,
    NorGate,
    NotGate,
    OrGate,
    OutputNode,
    Wire,
    XorGate,
)
from simulation import Circuit, SimulationEngine, format_truth_table

try:
    import requests
except ImportError:  # pragma: no cover - handled at runtime in UI callbacks
    requests = None

Component = Union[Gate, InputNode, OutputNode]
WireSource = Union[Gate, InputNode]
ConnectorType = Literal["gate_output", "gate_input", "input_output", "output_input", ""]
ComponentType = Optional[Literal["gate", "input", "output"]]
MAX_HISTORY_STEPS = 100


class CustomExpressionGate(Gate):
    """Gate implementation backed by a boolean expression from API custom-gate definitions."""

    def __init__(self, custom_name: str, input_names: list[str], expression: str):
        super().__init__(custom_name, num_inputs=max(1, len(input_names)))
        self.custom_name = custom_name
        self.input_names = input_names if input_names else ["IN1"]
        self.expression = expression

    def get_symbol(self) -> str:
        return self.custom_name.upper()

    def compute(self) -> Optional[bool]:
        if None in self.inputs:
            return None

        normalized = self.expression
        normalized = normalized.replace("¬", " not ")
        normalized = normalized.replace("∧", " and ")
        normalized = normalized.replace("∨", " or ")
        normalized = normalized.replace("⊕", " != ")

        if normalized == "0 (Always False)":
            return False
        if normalized == "1 (Always True)":
            return True

        context = {
            name: bool(value)
            for name, value in zip(self.input_names, self.inputs)
            if value is not None
        }
        context.update({"True": True, "False": False})

        try:
            return bool(eval(normalized, {"__builtins__": {}}, context))
        except Exception:
            return None


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
    API_BASE_URL = os.environ.get("LOGIC_API_URL", "http://127.0.0.1:8000")

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Visual Logic Gate Simulator")
        self.root.geometry("1200x800")
        self.root.configure(bg=self.COLORS["bg"])

        # Circuit and simulation
        self.circuit = Circuit()
        self.engine = SimulationEngine(self.circuit)

        # Interaction state
        self.selected_item: Optional[Component] = None
        self.dragging = False
        self.drag_offset: Tuple[float, float] = (0.0, 0.0)
        self.wiring_mode = False
        self.wire_start: Optional[WireSource] = None
        self.wire_start_type: Optional[Literal["gate_output", "input_output"]] = None
        self.temp_wire_id: Optional[int] = None

        # Counters for naming
        self.input_counter = 0
        self.output_counter = 0
        self.gate_counter = 0

        # Auth state for protected API routes
        self.auth_token = ""
        self.auth_user = ""
        self.auth_username_var = tk.StringVar(value="")
        self.auth_password_var = tk.StringVar(value="")
        self.auth_user_var = tk.StringVar(value="Current User: Guest")

        # Custom gate state loaded from API
        self.custom_gate_defs: dict[str, dict] = {}
        self.custom_gate_buttons_frame: Optional[ttk.Frame] = None

        # Undo/redo history
        self.history_past: list[dict] = []
        self.history_future: list[dict] = []
        self.drag_start_snapshot: Optional[dict] = None
        self.undo_btn: Optional[ttk.Button] = None
        self.redo_btn: Optional[ttk.Button] = None

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
        toolbox_shell = ttk.LabelFrame(parent, text="Components", padding=0)
        toolbox_shell.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        toolbox_canvas = tk.Canvas(toolbox_shell, highlightthickness=0, borderwidth=0)
        toolbox_scroll = ttk.Scrollbar(
            toolbox_shell, orient=tk.VERTICAL, command=toolbox_canvas.yview
        )
        toolbox_canvas.configure(yscrollcommand=toolbox_scroll.set, width=210)
        toolbox_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        toolbox_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        toolbox = ttk.Frame(toolbox_canvas, padding=10)
        toolbox_window = toolbox_canvas.create_window(
            (0, 0), window=toolbox, anchor="nw"
        )

        def _sync_toolbox_scroll_region(_event=None):
            toolbox_canvas.configure(scrollregion=toolbox_canvas.bbox("all"))
            toolbox_canvas.itemconfigure(
                toolbox_window, width=toolbox_canvas.winfo_width()
            )

        toolbox.bind("<Configure>", _sync_toolbox_scroll_region)
        toolbox_canvas.bind("<Configure>", _sync_toolbox_scroll_region)

        # Style for buttons
        style = ttk.Style()
        style.configure("Tool.TButton", padding=6)

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

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

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

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(toolbox, text="Custom Gates", font=("Arial", 10, "bold")).pack(
            pady=(0, 5)
        )

        ttk.Button(
            toolbox,
            text="Create Custom Gate",
            style="Tool.TButton",
            command=self._create_custom_gate_from_current_circuit,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="Share Custom Gate",
            style="Tool.TButton",
            command=self._share_custom_gate,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="Import Shared Gate",
            style="Tool.TButton",
            command=self._import_shared_custom_gate,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="Refresh Custom Gates",
            style="Tool.TButton",
            command=self._refresh_custom_gates,
        ).pack(fill=tk.X, pady=2)

        self.custom_gate_buttons_frame = ttk.Frame(toolbox)
        self.custom_gate_buttons_frame.pack(fill=tk.X, pady=(2, 0))

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # Actions section
        ttk.Label(toolbox, text="Actions", font=("Arial", 10, "bold")).pack(pady=(0, 5))

        self.wire_btn = ttk.Button(
            toolbox,
            text="🔗 Wire Mode: OFF",
            style="Tool.TButton",
            command=self._toggle_wire_mode,
        )
        self.wire_btn.pack(fill=tk.X, pady=2)

        self.undo_btn = ttk.Button(
            toolbox,
            text="↶ Undo (Ctrl+Z)",
            style="Tool.TButton",
            command=self._undo,
        )
        self.undo_btn.pack(fill=tk.X, pady=2)

        self.redo_btn = ttk.Button(
            toolbox,
            text="↷ Redo (Ctrl+Y)",
            style="Tool.TButton",
            command=self._redo,
        )
        self.redo_btn.pack(fill=tk.X, pady=2)

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

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

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
        ttk.Button(
            toolbox,
            text="⏱️ Timing Diagram",
            style="Tool.TButton",
            command=self._show_timing_diagram,
        ).pack(fill=tk.X, pady=2)

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(toolbox, text="Auth", font=("Arial", 10, "bold")).pack(pady=(0, 5))

        ttk.Label(toolbox, text="Username", font=("Arial", 9)).pack(anchor="w")
        ttk.Entry(toolbox, textvariable=self.auth_username_var).pack(fill=tk.X, pady=2)

        ttk.Label(toolbox, text="Password", font=("Arial", 9)).pack(anchor="w")
        ttk.Entry(toolbox, textvariable=self.auth_password_var, show="*").pack(
            fill=tk.X, pady=2
        )

        ttk.Button(
            toolbox,
            text="Register",
            style="Tool.TButton",
            command=self._register_auth,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="Login",
            style="Tool.TButton",
            command=self._login_auth,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="Logout",
            style="Tool.TButton",
            command=self._logout_auth,
        ).pack(fill=tk.X, pady=2)
        ttk.Label(
            toolbox,
            textvariable=self.auth_user_var,
            wraplength=180,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(2, 0))

        ttk.Separator(toolbox, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(toolbox, text="Persistence API", font=("Arial", 10, "bold")).pack(
            pady=(0, 5)
        )

        ttk.Button(
            toolbox,
            text="💾 Save To API",
            style="Tool.TButton",
            command=self._save_circuit_to_api,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="📂 Load From API",
            style="Tool.TButton",
            command=self._load_circuit_from_api,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="🔗 Share Saved Circuit",
            style="Tool.TButton",
            command=self._share_circuit_to_api,
        ).pack(fill=tk.X, pady=2)
        ttk.Button(
            toolbox,
            text="🌐 Load Shared Circuit",
            style="Tool.TButton",
            command=self._load_shared_circuit_from_api,
        ).pack(fill=tk.X, pady=2)

        self._render_custom_gate_buttons()
        self._update_history_button_state()

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
        self.root.bind("<Control-z>", self._on_undo_shortcut)
        self.root.bind("<Control-y>", self._on_redo_shortcut)
        self.root.bind("<Control-Shift-z>", self._on_redo_shortcut)
        self.root.bind("<Control-Shift-Z>", self._on_redo_shortcut)

    def _on_undo_shortcut(self, _event):
        self._undo()
        return "break"

    def _on_redo_shortcut(self, _event):
        self._redo()
        return "break"

    def _clone_snapshot(self, snapshot: dict) -> dict:
        return json.loads(json.dumps(snapshot))

    def _snapshot_signature(self, snapshot: dict) -> str:
        return json.dumps(snapshot, sort_keys=True)

    def _capture_snapshot(self) -> dict:
        return self._build_api_circuit_payload()

    def _push_undo_snapshot(self, snapshot: Optional[dict] = None) -> None:
        snapshot_to_store = self._clone_snapshot(snapshot or self._capture_snapshot())
        signature = self._snapshot_signature(snapshot_to_store)
        if (
            self.history_past
            and self._snapshot_signature(self.history_past[-1]) == signature
        ):
            self._update_history_button_state()
            return

        self.history_past.append(snapshot_to_store)
        if len(self.history_past) > MAX_HISTORY_STEPS:
            self.history_past = self.history_past[-MAX_HISTORY_STEPS:]
        self.history_future.clear()
        self._update_history_button_state()

    def _update_history_button_state(self) -> None:
        if self.undo_btn is not None:
            if self.history_past:
                self.undo_btn.state(["!disabled"])
            else:
                self.undo_btn.state(["disabled"])

        if self.redo_btn is not None:
            if self.history_future:
                self.redo_btn.state(["!disabled"])
            else:
                self.redo_btn.state(["disabled"])

    def _undo(self) -> None:
        if not self.history_past:
            self.status_var.set("Nothing to undo")
            self._update_history_button_state()
            return

        current = self._capture_snapshot()
        previous = self.history_past.pop()
        if self._snapshot_signature(current) != self._snapshot_signature(previous):
            self.history_future.insert(0, self._clone_snapshot(current))
            if len(self.history_future) > MAX_HISTORY_STEPS:
                self.history_future = self.history_future[:MAX_HISTORY_STEPS]

        self._apply_api_circuit_payload(self._clone_snapshot(previous))
        self.status_var.set("Undo applied")
        self._update_history_button_state()

    def _redo(self) -> None:
        if not self.history_future:
            self.status_var.set("Nothing to redo")
            self._update_history_button_state()
            return

        current = self._capture_snapshot()
        next_snapshot = self.history_future.pop(0)
        if self._snapshot_signature(current) != self._snapshot_signature(next_snapshot):
            self.history_past.append(self._clone_snapshot(current))
            if len(self.history_past) > MAX_HISTORY_STEPS:
                self.history_past = self.history_past[-MAX_HISTORY_STEPS:]

        self._apply_api_circuit_payload(self._clone_snapshot(next_snapshot))
        self.status_var.set("Redo applied")
        self._update_history_button_state()

    def _render_custom_gate_buttons(self) -> None:
        if self.custom_gate_buttons_frame is None:
            return

        for child in self.custom_gate_buttons_frame.winfo_children():
            child.destroy()

        if not self.custom_gate_defs:
            ttk.Label(
                self.custom_gate_buttons_frame,
                text="No custom gates yet",
                wraplength=180,
                justify=tk.LEFT,
            ).pack(fill=tk.X, pady=(2, 0))
            return

        for gate_name in sorted(self.custom_gate_defs.keys()):
            gate_def = self.custom_gate_defs[gate_name]
            input_names = gate_def.get("input_names", [])
            ttk.Button(
                self.custom_gate_buttons_frame,
                text=f"{gate_name.upper()} ({len(input_names)} in)",
                style="Tool.TButton",
                command=lambda n=gate_name: self._add_component(f"custom:{n}"),
            ).pack(fill=tk.X, pady=2)

    def _refresh_custom_gates(self, silent: bool = False) -> None:
        if not self._require_requests():
            return

        if not self.auth_token:
            self.custom_gate_defs = {}
            self._render_custom_gate_buttons()
            if not silent:
                self.status_var.set("Sign in to load custom gates")
            return

        try:
            response = requests.get(
                f"{self.API_BASE_URL}/api/custom-gates",
                headers=self._auth_headers_optional(),
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(
                    response, "Could not load custom gates"
                )
                raise RuntimeError(detail)

            gates = response.json().get("gates", [])
            next_defs: dict[str, dict] = {}
            for gate in gates:
                name = str(gate.get("name", "")).strip().lower()
                if not name:
                    continue
                next_defs[name] = {
                    "name": name,
                    "input_names": list(gate.get("input_names", [])),
                    "expression": str(gate.get("expression", "")),
                }

            self.custom_gate_defs = next_defs
            self._render_custom_gate_buttons()
            if not silent:
                self.status_var.set(
                    f"Loaded {len(self.custom_gate_defs)} custom gate(s)"
                )
        except Exception as error:  # pragma: no cover - network/UI path
            if not silent:
                messagebox.showerror(
                    "Custom Gates",
                    f"Could not load custom gates.\n\n{error}",
                )

    def _create_custom_gate_from_current_circuit(self) -> None:
        if not self._require_requests():
            return

        headers = self._auth_headers_required()
        if headers is None:
            return

        if not self.circuit.input_nodes or not self.circuit.output_nodes:
            messagebox.showwarning(
                "Create Custom Gate",
                "Add at least one input and one output before creating a custom gate.",
            )
            return

        gate_name = simpledialog.askstring(
            "Create Custom Gate",
            "Enter custom gate name:",
            parent=self.root,
        )
        if not gate_name:
            return

        available_outputs = [node.name for node in self.circuit.output_nodes]
        output_name = simpledialog.askstring(
            "Create Custom Gate",
            (
                "Optional: output name to derive expression from.\n"
                f"Available outputs: {', '.join(available_outputs)}\n"
                "Leave blank to use first output."
            ),
            parent=self.root,
        )

        body = {
            "name": gate_name.strip().lower(),
            "output_name": (output_name.strip() if output_name else None),
            "circuit": self._build_api_circuit_payload(),
        }

        try:
            response = requests.post(
                f"{self.API_BASE_URL}/api/custom-gates/create",
                headers={"Content-Type": "application/json", **headers},
                json=body,
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(
                    response, "Could not create custom gate"
                )
                raise RuntimeError(detail)

            created = response.json().get("name", gate_name.strip().lower())
            self._refresh_custom_gates(silent=True)
            self.status_var.set(f"Custom gate '{created}' created")
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror(
                "Create Custom Gate Failed",
                f"Could not create custom gate.\n\n{error}",
            )

    def _share_custom_gate(self) -> None:
        if not self._require_requests():
            return

        headers = self._auth_headers_required()
        if headers is None:
            return

        if not self.custom_gate_defs:
            self._refresh_custom_gates(silent=True)
        if not self.custom_gate_defs:
            messagebox.showwarning("Share Custom Gate", "No custom gates to share")
            return

        available_names = sorted(self.custom_gate_defs.keys())
        selected = simpledialog.askstring(
            "Share Custom Gate",
            (
                f"Available: {', '.join(available_names)}\n\n"
                "Enter custom gate name to share:"
            ),
            parent=self.root,
        )
        if not selected:
            return
        gate_name = selected.strip().lower()
        if gate_name not in self.custom_gate_defs:
            messagebox.showwarning(
                "Share Custom Gate",
                f"Custom gate '{gate_name}' is not available.",
            )
            return

        try:
            response = requests.post(
                f"{self.API_BASE_URL}/api/custom-gates/share/{quote(gate_name, safe='')}",
                headers=headers,
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(
                    response, "Could not share custom gate"
                )
                raise RuntimeError(detail)

            payload = response.json()
            share_path = str(payload.get("share_path", ""))
            share_link = share_path
            if share_path.startswith("/"):
                share_link = f"{self.API_BASE_URL.rstrip('/')}{share_path}"

            if share_link:
                self.root.clipboard_clear()
                self.root.clipboard_append(share_link)

            self.status_var.set(f"Custom gate '{gate_name}' shared")
            messagebox.showinfo(
                "Share Custom Gate",
                (
                    f"Share ID: {payload.get('share_id', '(unknown)')}\n\n"
                    f"Link: {share_link or '(not provided)'}\n\n"
                    "Link copied to clipboard."
                ),
            )
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror(
                "Share Custom Gate Failed",
                f"Could not share custom gate.\n\n{error}",
            )

    def _extract_gate_share_id(self, raw_value: str) -> str:
        raw = raw_value.strip()
        if not raw:
            return ""

        if "gateShare=" in raw:
            try:
                parsed = urlparse(raw)
                share_id = parse_qs(parsed.query).get("gateShare", [""])[0]
                if share_id:
                    return share_id
            except Exception:
                pass
            return raw.split("gateShare=", 1)[1].split("&", 1)[0]

        return raw

    def _import_shared_custom_gate(self) -> None:
        if not self._require_requests():
            return

        headers = self._auth_headers_required()
        if headers is None:
            return

        raw_share = simpledialog.askstring(
            "Import Shared Gate",
            "Enter custom gate share ID or link (?gateShare=...):",
            parent=self.root,
        )
        if not raw_share:
            return

        share_id = self._extract_gate_share_id(raw_share)
        if not share_id:
            messagebox.showwarning("Import Shared Gate", "Invalid share ID or link")
            return

        rename = simpledialog.askstring(
            "Import Shared Gate",
            "Optional: new local name (leave blank to keep source name):",
            parent=self.root,
        )
        body = {}
        if rename and rename.strip():
            body["name"] = rename.strip().lower()

        try:
            response = requests.post(
                f"{self.API_BASE_URL}/api/custom-gates/import/{quote(share_id, safe='')}",
                headers={"Content-Type": "application/json", **headers},
                json=body,
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(
                    response, "Could not import shared custom gate"
                )
                raise RuntimeError(detail)

            payload = response.json()
            self._refresh_custom_gates(silent=True)
            self.status_var.set(
                f"Imported custom gate '{payload.get('name', '(unknown)')}'"
            )
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror(
                "Import Shared Gate Failed",
                f"Could not import shared custom gate.\n\n{error}",
            )

    def _add_component(self, component_type: str):
        """Add a new component to the circuit"""
        x, y = 100, 100 + len(self.circuit.get_all_components()) * 80

        if component_type == "input":
            self._push_undo_snapshot()
            self.input_counter += 1
            node = InputNode(f"IN{self.input_counter}")
            node.move_to(x, y)
            self.circuit.add_input(node)
            self._draw_input_node(node)

        elif component_type == "output":
            self._push_undo_snapshot()
            self.output_counter += 1
            node = OutputNode(f"OUT{self.output_counter}")
            node.move_to(x + 400, y)
            self.circuit.add_output(node)
            self._draw_output_node(node)

        elif component_type.startswith("custom:"):
            custom_name = component_type.split(":", 1)[1].strip().lower()
            gate_def = self.custom_gate_defs.get(custom_name)
            if gate_def is None and self.auth_token:
                self._refresh_custom_gates(silent=True)
                gate_def = self.custom_gate_defs.get(custom_name)

            if gate_def is None:
                messagebox.showwarning(
                    "Custom Gate",
                    f"Custom gate '{custom_name}' is not available. Refresh and try again.",
                )
                return

            self._push_undo_snapshot()
            self.gate_counter += 1
            gate = CustomExpressionGate(
                custom_name,
                list(gate_def.get("input_names", [])),
                str(gate_def.get("expression", "")),
            )
            gate.name = f"{custom_name.upper()}{self.gate_counter}"
            gate.move_to(x + 150, y)
            self.circuit.add_gate(gate)
            self._draw_gate(gate)

        else:
            self._push_undo_snapshot()
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
        start_x, start_y = wire.get_start_pos()
        end_x, end_y = wire.get_end_pos()

        # Determine wire color based on value
        value = wire.get_value()
        if value is None:
            color = self.COLORS["wire"]
        elif value:
            color = self.COLORS["wire_on"]
        else:
            color = self.COLORS["wire_off"]

        # Draw curved wire
        mid_x = (start_x + end_x) / 2
        line_coords = [
            int(start_x),
            int(start_y),
            int(mid_x),
            int(start_y),
            int(mid_x),
            int(end_y),
            int(end_x),
            int(end_y),
        ]

        wire.canvas_id = self.canvas.create_line(
            *line_coords,
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

    def _find_component_at(
        self, x: float, y: float
    ) -> Tuple[Optional[Component], ComponentType]:
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

    def _find_connector_at(
        self, x: float, y: float
    ) -> Tuple[Optional[Component], ConnectorType, int]:
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
        x: float = float(self.canvas.canvasx(event.x))
        y: float = float(self.canvas.canvasy(event.y))

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
            self.drag_start_snapshot = self._capture_snapshot()
            if comp_type is not None:
                self._update_properties(component, comp_type)
        else:
            self.selected_item = None
            self.drag_start_snapshot = None
            self._clear_properties()

        self._redraw_all()

    def _handle_wiring_click(self, x: float, y: float):
        """Handle click in wiring mode"""
        component, conn_type, index = self._find_connector_at(x, y)

        if component is None:
            self.status_var.set("Click on a connector to start/end wire")
            return

        if self.wire_start is None:
            # Start wiring - must be an output connector
            if conn_type in ("gate_output", "input_output") and isinstance(
                component, (Gate, InputNode)
            ):
                self.wire_start = component
                self.wire_start_type = conn_type
                self.status_var.set(
                    f"Wiring from {getattr(component, 'name', 'component')} - click on an input connector"
                )
            else:
                self.status_var.set("Start wire from an OUTPUT connector")
        else:
            # End wiring - must be an input connector
            if conn_type in ("gate_input", "output_input") and isinstance(
                component, (Gate, OutputNode)
            ):
                # Create wire
                if self.wire_start_type == "input_output":
                    source_type: Literal["input", "gate"] = "input"
                else:
                    source_type = "gate"

                if conn_type == "output_input":
                    target_type: Literal["output", "gate"] = "output"
                else:
                    target_type = "gate"

                self._push_undo_snapshot()
                wire = Wire(self.wire_start, source_type, component, target_type, index)
                self.circuit.add_wire(wire)

                self.status_var.set("Wire connected!")
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

        x: float = float(self.canvas.canvasx(event.x))
        y: float = float(self.canvas.canvasy(event.y))

        new_x = x - self.drag_offset[0]
        new_y = y - self.drag_offset[1]

        self.selected_item.move_to(new_x, new_y)
        self._redraw_all()

    def _on_canvas_release(self, event):
        """Handle canvas release"""
        if self.drag_start_snapshot is not None:
            current_signature = self._snapshot_signature(self._capture_snapshot())
            start_signature = self._snapshot_signature(self.drag_start_snapshot)
            if current_signature != start_signature:
                self._push_undo_snapshot(self.drag_start_snapshot)
        self.drag_start_snapshot = None
        self.dragging = False

    def _on_double_click(self, event):
        """Handle double click - toggle input nodes"""
        x: float = float(self.canvas.canvasx(event.x))
        y: float = float(self.canvas.canvasy(event.y))

        component, comp_type = self._find_component_at(x, y)

        if comp_type == "input" and isinstance(component, InputNode):
            self._push_undo_snapshot()
            component.toggle()
            self._run_simulation()
            self._redraw_all()

    def _on_mouse_move(self, event):
        """Handle mouse movement for wire preview"""
        if not self.wiring_mode or self.wire_start is None:
            return

        x: float = float(self.canvas.canvasx(event.x))
        y: float = float(self.canvas.canvasy(event.y))

        # Draw temporary wire
        if self.temp_wire_id:
            self.canvas.delete(self.temp_wire_id)

        start_source = self.wire_start
        start_x, start_y = start_source.get_output_position()
        mid_x = (start_x + x) / 2
        preview_coords = [
            int(start_x),
            int(start_y),
            int(mid_x),
            int(start_y),
            int(mid_x),
            int(y),
            int(x),
            int(y),
        ]

        self.temp_wire_id = self.canvas.create_line(
            *preview_coords,
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

        self._push_undo_snapshot()

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
            self._push_undo_snapshot()
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

    def _show_timing_diagram(self):
        """Generate and show timing diagram from API."""
        if not self._require_requests():
            return

        body = {"circuit": self._build_api_circuit_payload()}
        headers = self._auth_headers_optional()

        try:
            response = requests.post(
                f"{self.API_BASE_URL}/api/circuit/timing",
                json=body,
                headers=headers,
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(
                    response, "Could not generate timing diagram"
                )
                raise RuntimeError(detail)

            timing = response.json()
            steps = timing.get("steps", [])
            signals = timing.get("signals", [])
            if not steps or not signals:
                text = "Run simulation to generate a timing diagram."
            else:
                step_line = "Step: " + " ".join(str(step) for step in steps)
                signal_lines = []
                for signal in signals:
                    name = str(signal.get("name", "signal"))
                    values = signal.get("values", [])
                    waveform = " ".join(
                        "?" if value is None else ("-" if bool(value) else "_")
                        for value in values
                    )
                    signal_lines.append(f"{name.ljust(10, ' ')}: {waveform}")
                text = "\n".join([step_line, *signal_lines])

            popup = tk.Toplevel(self.root)
            popup.title("Timing Diagram")
            popup.geometry("520x500")
            popup.configure(bg=self.COLORS["bg"])

            text_widget = scrolledtext.ScrolledText(
                popup,
                font=("Consolas", 12),
                bg=self.COLORS["panel_bg"],
                fg=self.COLORS["gate_text"],
            )
            text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text_widget.insert("1.0", text)
            text_widget.config(state=tk.DISABLED)
            self.status_var.set("Timing diagram ready")
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror(
                "Timing Diagram Failed",
                f"Could not generate timing diagram.\n\n{error}",
            )

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

    def _update_properties(
        self, component: Component, comp_type: Literal["gate", "input", "output"]
    ):
        """Update the properties panel"""
        self.props_text.config(state=tk.NORMAL)
        self.props_text.delete("1.0", tk.END)

        if comp_type == "gate" and isinstance(component, Gate):
            props = f"""Gate: {component.get_symbol()}
Name: {component.name}
Inputs: {component.num_inputs}
Input Values: {component.inputs}
Output: {component.get_output()}
Position: ({component.x}, {component.y})
"""
        elif comp_type == "input" and isinstance(component, InputNode):
            props = f"""Input Node
Name: {component.name}
Value: {component.value} ({'HIGH' if component.value else 'LOW'})
Position: ({component.x}, {component.y})

Double-click to toggle!
"""
        elif comp_type == "output" and isinstance(component, OutputNode):
            props = f"""Output Node
Name: {component.name}
Value: {component.value}
Position: ({component.x}, {component.y})
"""
        else:
            props = "Unknown component"

        self.props_text.insert("1.0", props)
        self.props_text.config(state=tk.DISABLED)

    def _build_api_circuit_payload(self) -> dict:
        gate_type_map = {
            AndGate: "and",
            OrGate: "or",
            NotGate: "not",
            NandGate: "nand",
            NorGate: "nor",
            XorGate: "xor",
        }

        input_ids = {
            node: f"in_{index + 1}"
            for index, node in enumerate(self.circuit.input_nodes)
        }
        output_ids = {
            node: f"out_{index + 1}"
            for index, node in enumerate(self.circuit.output_nodes)
        }
        gate_ids = {
            gate: f"g_{index + 1}" for index, gate in enumerate(self.circuit.gates)
        }

        payload = {
            "inputs": [
                {
                    "id": input_ids[node],
                    "name": node.name,
                    "value": node.value,
                    "x": node.x,
                    "y": node.y,
                }
                for node in self.circuit.input_nodes
            ],
            "outputs": [
                {
                    "id": output_ids[node],
                    "name": node.name,
                    "x": node.x,
                    "y": node.y,
                }
                for node in self.circuit.output_nodes
            ],
            "gates": [],
            "wires": [],
        }

        for gate in self.circuit.gates:
            gate_type = gate_type_map.get(type(gate))
            if gate_type is None and isinstance(gate, CustomExpressionGate):
                gate_type = f"custom:{gate.custom_name}"
            if gate_type is None:
                continue

            payload["gates"].append(
                {
                    "id": gate_ids[gate],
                    "type": gate_type,
                    "name": gate.name,
                    "x": gate.x,
                    "y": gate.y,
                }
            )

        for wire in self.circuit.wires:
            if isinstance(wire.source, InputNode):
                source_id = input_ids.get(wire.source)
            else:
                source_id = gate_ids.get(wire.source)

            if isinstance(wire.target, OutputNode):
                target_id = output_ids.get(wire.target)
            else:
                target_id = gate_ids.get(wire.target)

            if source_id is None or target_id is None:
                continue

            payload["wires"].append(
                {
                    "source_id": source_id,
                    "source_type": wire.source_type,
                    "target_id": target_id,
                    "target_type": wire.target_type,
                    "target_input_index": wire.target_input_index,
                }
            )

        return payload

    def _require_requests(self) -> bool:
        if requests is None:
            messagebox.showerror(
                "Dependency Missing",
                "The 'requests' package is required. Install it with: pip install requests",
            )
            return False
        return True

    def _auth_headers_required(self) -> Optional[dict]:
        if not self.auth_token:
            messagebox.showwarning(
                "Authentication Required",
                "Sign in from the Auth section before using this API action.",
            )
            return None
        return {"Authorization": f"Bearer {self.auth_token}"}

    def _auth_headers_optional(self) -> dict:
        if not self.auth_token:
            return {}
        return {"Authorization": f"Bearer {self.auth_token}"}

    def _extract_error_detail(self, response, fallback: str) -> str:
        try:
            payload = response.json()
        except Exception:
            return fallback

        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail
        return fallback

    def _set_auth_state(self, token: str, username: str) -> None:
        self.auth_token = token
        self.auth_user = username
        self.auth_user_var.set(
            f"Current User: {username}" if username else "Current User: Guest"
        )
        if username:
            self._refresh_custom_gates(silent=True)
        else:
            self.custom_gate_defs = {}
            self._render_custom_gate_buttons()

    def _submit_auth(self, endpoint: str) -> None:
        if not self._require_requests():
            return

        username = self.auth_username_var.get().strip().lower()
        password = self.auth_password_var.get().strip()
        if not username or not password:
            messagebox.showwarning("Authentication", "Enter username and password.")
            return

        try:
            response = requests.post(
                f"{self.API_BASE_URL}{endpoint}",
                json={"username": username, "password": password},
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(response, "Authentication failed")
                raise RuntimeError(detail)

            data = response.json()
            token = data.get("access_token", "")
            user = data.get("username", username)
            if not token:
                raise RuntimeError("Authentication token missing in server response")

            self._set_auth_state(token, user)
            self.auth_password_var.set("")
            self.status_var.set(f"Signed in as {user}")
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror("Authentication Failed", f"{error}")

    def _register_auth(self) -> None:
        self._submit_auth("/api/auth/register")

    def _login_auth(self) -> None:
        self._submit_auth("/api/auth/login")

    def _logout_auth(self) -> None:
        self._set_auth_state("", "")
        self.auth_password_var.set("")
        self.status_var.set("Signed out")

    def _prompt_saved_circuit_name(self, headers: dict, title: str) -> Optional[str]:
        try:
            list_response = requests.get(
                f"{self.API_BASE_URL}/api/circuit/list",
                headers=headers,
                timeout=8,
            )
            if not list_response.ok:
                detail = self._extract_error_detail(
                    list_response, "Could not list saved circuits"
                )
                raise RuntimeError(detail)
            available = list_response.json().get("circuits", [])
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror(title, f"Could not list saved circuits.\n\n{error}")
            return None

        prompt = "Enter circuit name:"
        if available:
            prompt = f"Available: {', '.join(available)}\n\nEnter circuit name:"

        name = simpledialog.askstring(title, prompt, parent=self.root)
        if not name:
            return None
        return name.strip()

    def _extract_share_id(self, raw_value: str) -> str:
        raw = raw_value.strip()
        if not raw:
            return ""

        if "share=" in raw:
            try:
                parsed = urlparse(raw)
                share_id = parse_qs(parsed.query).get("share", [""])[0]
                if share_id:
                    return share_id
            except Exception:
                pass
            return raw.split("share=", 1)[1].split("&", 1)[0]

        return raw

    def _apply_api_circuit_payload(self, circuit_payload: dict) -> None:
        self.circuit.clear()
        self.selected_item = None
        self.drag_start_snapshot = None
        self._clear_properties()

        input_lookup = {}
        output_lookup = {}
        gate_lookup = {}

        gate_classes = {
            "and": AndGate,
            "or": OrGate,
            "not": NotGate,
            "nand": NandGate,
            "nor": NorGate,
            "xor": XorGate,
        }

        self.input_counter = 0
        self.output_counter = 0
        self.gate_counter = 0

        if self.auth_token:
            self._refresh_custom_gates(silent=True)

        missing_custom_gates = set()

        for input_spec in circuit_payload.get("inputs", []):
            node = InputNode(
                input_spec.get("name", "IN"), input_spec.get("value", False)
            )
            node.move_to(input_spec.get("x", 100), input_spec.get("y", 100))
            self.circuit.add_input(node)
            input_lookup[input_spec["id"]] = node
            self.input_counter += 1

        for output_spec in circuit_payload.get("outputs", []):
            node = OutputNode(output_spec.get("name", "OUT"))
            node.move_to(output_spec.get("x", 500), output_spec.get("y", 100))
            self.circuit.add_output(node)
            output_lookup[output_spec["id"]] = node
            self.output_counter += 1

        for gate_spec in circuit_payload.get("gates", []):
            gate_type = gate_spec.get("type", "and")
            gate = None

            if isinstance(gate_type, str) and gate_type.startswith("custom:"):
                custom_name = gate_type.split(":", 1)[1].strip().lower()
                gate_def = self.custom_gate_defs.get(custom_name)
                if gate_def is not None:
                    gate = CustomExpressionGate(
                        custom_name,
                        list(gate_def.get("input_names", [])),
                        str(gate_def.get("expression", "")),
                    )
                    gate.name = gate_spec.get("name", custom_name.upper())
                else:
                    missing_custom_gates.add(custom_name)
                    continue
            else:
                gate_class = gate_classes.get(gate_type)
                if gate_class is None:
                    continue
                gate = gate_class(gate_spec.get("name", str(gate_type).upper()))

            gate.move_to(gate_spec.get("x", 250), gate_spec.get("y", 150))
            self.circuit.add_gate(gate)
            gate_lookup[gate_spec["id"]] = gate
            self.gate_counter += 1

        for wire_spec in circuit_payload.get("wires", []):
            source = (
                input_lookup.get(wire_spec.get("source_id"))
                if wire_spec.get("source_type") == "input"
                else gate_lookup.get(wire_spec.get("source_id"))
            )
            target = (
                output_lookup.get(wire_spec.get("target_id"))
                if wire_spec.get("target_type") == "output"
                else gate_lookup.get(wire_spec.get("target_id"))
            )

            if source is None or target is None:
                continue

            self.circuit.add_wire(
                Wire(
                    source=source,
                    source_type=wire_spec.get("source_type", "gate"),
                    target=target,
                    target_type=wire_spec.get("target_type", "gate"),
                    target_input_index=wire_spec.get("target_input_index", 0),
                )
            )

        self._run_simulation()
        if missing_custom_gates:
            missing_list = ", ".join(sorted(missing_custom_gates))
            messagebox.showwarning(
                "Custom Gates Missing",
                (
                    "Some custom gates used by this circuit are not available "
                    f"for the current desktop session: {missing_list}"
                ),
            )

    def _save_circuit_to_api(self):
        if not self._require_requests():
            return

        headers = self._auth_headers_required()
        if headers is None:
            return

        name = simpledialog.askstring(
            "Save Circuit",
            "Enter circuit name (letters, numbers, _ and - only):",
            parent=self.root,
        )
        if not name:
            return

        body = {
            "name": name,
            "circuit": self._build_api_circuit_payload(),
        }

        try:
            response = requests.post(
                f"{self.API_BASE_URL}/api/circuit/save",
                json=body,
                headers=headers,
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(response, "Could not save circuit")
                raise RuntimeError(detail)
            self.status_var.set(f"Saved circuit '{name}' to API storage")
            messagebox.showinfo("Saved", f"Circuit '{name}' saved successfully.")
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror("Save Failed", f"Could not save circuit.\n\n{error}")

    def _load_circuit_from_api(self):
        if not self._require_requests():
            return

        headers = self._auth_headers_required()
        if headers is None:
            return

        name = self._prompt_saved_circuit_name(headers, "Load Circuit")
        if not name:
            return

        try:
            encoded_name = quote(name.strip(), safe="")
            response = requests.get(
                f"{self.API_BASE_URL}/api/circuit/load/{encoded_name}",
                headers=headers,
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(response, "Could not load circuit")
                raise RuntimeError(detail)
            payload = response.json().get("circuit", {})
            self._push_undo_snapshot()
            self._apply_api_circuit_payload(payload)
            self.status_var.set(f"Loaded circuit '{name}' from API storage")
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror("Load Failed", f"Could not load circuit.\n\n{error}")

    def _share_circuit_to_api(self):
        if not self._require_requests():
            return

        headers = self._auth_headers_required()
        if headers is None:
            return

        name = self._prompt_saved_circuit_name(headers, "Share Circuit")
        if not name:
            return

        try:
            encoded_name = quote(name, safe="")
            response = requests.post(
                f"{self.API_BASE_URL}/api/circuit/share/{encoded_name}",
                headers=headers,
                timeout=8,
            )
            if not response.ok:
                detail = self._extract_error_detail(response, "Could not share circuit")
                raise RuntimeError(detail)

            data = response.json()
            share_path = str(data.get("share_path", ""))
            share_link = share_path
            if share_path.startswith("/"):
                share_link = f"{self.API_BASE_URL.rstrip('/')}{share_path}"

            if share_link:
                self.root.clipboard_clear()
                self.root.clipboard_append(share_link)

            self.status_var.set(f"Share link created for '{name}'")
            messagebox.showinfo(
                "Share Circuit",
                (
                    f"Share ID: {data.get('share_id', '(unknown)')}\n\n"
                    f"Link: {share_link or '(not provided)'}\n\n"
                    "Link copied to clipboard."
                ),
            )
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror("Share Failed", f"Could not share circuit.\n\n{error}")

    def _load_shared_circuit_from_api(self):
        if not self._require_requests():
            return

        raw_share = simpledialog.askstring(
            "Load Shared Circuit",
            "Enter share ID or full link (?share=...):",
            parent=self.root,
        )
        if not raw_share:
            return

        share_id = self._extract_share_id(raw_share)
        if not share_id:
            messagebox.showwarning("Load Shared Circuit", "Invalid share ID or link.")
            return

        try:
            encoded_share_id = quote(share_id, safe="")
            response = requests.get(
                f"{self.API_BASE_URL}/api/public/circuit/{encoded_share_id}", timeout=8
            )
            if not response.ok:
                detail = self._extract_error_detail(
                    response, "Could not load shared circuit"
                )
                raise RuntimeError(detail)

            payload = response.json().get("circuit", {})
            self._push_undo_snapshot()
            self._apply_api_circuit_payload(payload)
            self.status_var.set("Loaded shared circuit")
        except Exception as error:  # pragma: no cover - network/UI path
            messagebox.showerror(
                "Load Shared Failed",
                f"Could not load shared circuit.\n\n{error}",
            )

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
