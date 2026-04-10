"""
FastAPI backend for the Logic Gate Simulator.

This module exposes the existing simulation engine through HTTP APIs so
multiple clients (Tkinter desktop app, React web app, etc.) can share the
same backend logic.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, cast

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
from simulation import Circuit, SimulationEngine


class GateSpec(BaseModel):
    id: str = Field(..., description="Unique gate identifier")
    type: Literal["and", "or", "not", "nand", "nor", "xor"]
    name: Optional[str] = None
    x: float = 0.0
    y: float = 0.0


class InputSpec(BaseModel):
    id: str = Field(..., description="Unique input identifier")
    name: str
    value: bool = False
    x: float = 0.0
    y: float = 0.0


class OutputSpec(BaseModel):
    id: str = Field(..., description="Unique output identifier")
    name: str
    x: float = 0.0
    y: float = 0.0


class WireSpec(BaseModel):
    source_id: str
    source_type: Literal["input", "gate"]
    target_id: str
    target_type: Literal["gate", "output"]
    target_input_index: int = 0


class CircuitPayload(BaseModel):
    inputs: List[InputSpec] = Field(default_factory=list)
    outputs: List[OutputSpec] = Field(default_factory=list)
    gates: List[GateSpec] = Field(default_factory=list)
    wires: List[WireSpec] = Field(default_factory=list)


class SimulationRequest(BaseModel):
    circuit: CircuitPayload


class SaveCircuitRequest(BaseModel):
    name: str = Field(..., description="Circuit file key, e.g. half_adder")
    circuit: CircuitPayload


class SaveCircuitResponse(BaseModel):
    name: str
    saved: bool


class CircuitListResponse(BaseModel):
    circuits: List[str]


class GateEvaluateRequest(BaseModel):
    gate_type: Literal["and", "or", "not", "nand", "nor", "xor"]
    inputs: List[bool]


class TruthTableResponse(BaseModel):
    input_names: List[str]
    output_names: List[str]
    rows: List[List[bool]]


class SimulationResponse(BaseModel):
    gate_outputs: Dict[str, Optional[bool]]
    output_values: Dict[str, Optional[bool]]
    truth_table: TruthTableResponse
    expressions: Dict[str, str]


app = FastAPI(title="Logic Gate Simulator API", version="1.0.0")

_cors_origins_raw = os.environ.get(
    "LOGIC_API_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
)
_cors_origins = [
    origin.strip() for origin in _cors_origins_raw.split(",") if origin.strip()
]
_allow_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


GATE_CLASSES = {
    "and": AndGate,
    "or": OrGate,
    "not": NotGate,
    "nand": NandGate,
    "nor": NorGate,
    "xor": XorGate,
}

PROJECT_DIR = Path(__file__).resolve().parent
CIRCUITS_DIR = PROJECT_DIR / "data" / "circuits"
VALID_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
SUPABASE_URL = os.environ.get("LOGIC_SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("LOGIC_SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TABLE = os.environ.get("LOGIC_SUPABASE_TABLE", "circuits")
SUPABASE_TIMEOUT_SECONDS = 8.0


def _supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _supabase_base_url() -> str:
    return f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"


def _supabase_headers(prefer: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _ensure_storage_dir() -> None:
    CIRCUITS_DIR.mkdir(parents=True, exist_ok=True)


def _validate_circuit_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Circuit name cannot be empty")
    if not VALID_NAME.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail="Circuit name must match [A-Za-z0-9_-]",
        )
    return normalized


def _circuit_file_path(name: str) -> Path:
    safe_name = _validate_circuit_name(name)
    return CIRCUITS_DIR / f"{safe_name}.json"


def _list_saved_circuits_supabase() -> List[str]:
    try:
        with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
            response = client.get(
                _supabase_base_url(),
                params={"select": "name", "order": "name.asc"},
                headers=_supabase_headers(),
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase list failed: {error}",
        ) from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase list failed: {response.text}",
        )

    rows = response.json()
    return sorted(
        row["name"]
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    )


def _save_circuit_supabase(name: str, circuit_payload: CircuitPayload) -> None:
    safe_name = _validate_circuit_name(name)
    payload = [{"name": safe_name, "circuit": circuit_payload.model_dump()}]

    try:
        with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
            response = client.post(
                _supabase_base_url(),
                params={"on_conflict": "name"},
                headers=_supabase_headers(
                    prefer="resolution=merge-duplicates,return=minimal"
                ),
                json=payload,
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase save failed: {error}",
        ) from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase save failed: {response.text}",
        )


def _load_circuit_supabase(name: str) -> Dict[str, object]:
    safe_name = _validate_circuit_name(name)

    try:
        with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
            response = client.get(
                _supabase_base_url(),
                params={"select": "circuit", "name": f"eq.{safe_name}", "limit": "1"},
                headers=_supabase_headers(),
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase load failed: {error}",
        ) from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase load failed: {response.text}",
        )

    rows = response.json()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Circuit '{safe_name}' not found")

    circuit_data = rows[0].get("circuit")
    if not isinstance(circuit_data, dict):
        raise HTTPException(
            status_code=500,
            detail="Saved circuit payload is invalid",
        )

    return circuit_data


def _build_circuit(
    payload: CircuitPayload,
) -> Tuple[Circuit, Dict[str, Gate], Dict[str, InputNode], Dict[str, OutputNode]]:
    circuit = Circuit()
    gates_by_id: Dict[str, Gate] = {}
    inputs_by_id: Dict[str, InputNode] = {}
    outputs_by_id: Dict[str, OutputNode] = {}

    for input_spec in payload.inputs:
        node = InputNode(name=input_spec.name, value=input_spec.value)
        node.move_to(input_spec.x, input_spec.y)
        circuit.add_input(node)
        inputs_by_id[input_spec.id] = node

    for output_spec in payload.outputs:
        node = OutputNode(name=output_spec.name)
        node.move_to(output_spec.x, output_spec.y)
        circuit.add_output(node)
        outputs_by_id[output_spec.id] = node

    for gate_spec in payload.gates:
        gate_class = GATE_CLASSES[gate_spec.type]
        gate_name = gate_spec.name or gate_spec.id.upper()
        gate = gate_class(gate_name)
        gate.move_to(gate_spec.x, gate_spec.y)
        circuit.add_gate(gate)
        gates_by_id[gate_spec.id] = gate

    for wire_spec in payload.wires:
        source = (
            inputs_by_id.get(wire_spec.source_id)
            if wire_spec.source_type == "input"
            else gates_by_id.get(wire_spec.source_id)
        )
        target = (
            outputs_by_id.get(wire_spec.target_id)
            if wire_spec.target_type == "output"
            else gates_by_id.get(wire_spec.target_id)
        )

        if source is None:
            raise HTTPException(
                status_code=400, detail=f"Invalid wire source_id: {wire_spec.source_id}"
            )
        if target is None:
            raise HTTPException(
                status_code=400, detail=f"Invalid wire target_id: {wire_spec.target_id}"
            )

        if wire_spec.target_type == "gate":
            if not isinstance(target, Gate):
                raise HTTPException(
                    status_code=400,
                    detail=f"Wire target {wire_spec.target_id} must be a gate",
                )

            gate_target = cast(Gate, target)

            if wire_spec.target_input_index >= gate_target.num_inputs:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"target_input_index {wire_spec.target_input_index} out of range for "
                        f"gate {wire_spec.target_id} with {gate_target.num_inputs} input(s)"
                    ),
                )

        circuit.add_wire(
            Wire(
                source=source,
                source_type=wire_spec.source_type,
                target=target,
                target_type=wire_spec.target_type,
                target_input_index=wire_spec.target_input_index,
            )
        )

    return circuit, gates_by_id, inputs_by_id, outputs_by_id


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/storage/info")
def storage_info() -> Dict[str, str]:
    return {
        "mode": "supabase" if _supabase_enabled() else "filesystem",
        "table": SUPABASE_TABLE if _supabase_enabled() else "data/circuits",
    }


@app.get("/api/circuit/list", response_model=CircuitListResponse)
def list_saved_circuits() -> CircuitListResponse:
    if _supabase_enabled():
        return CircuitListResponse(circuits=_list_saved_circuits_supabase())

    _ensure_storage_dir()
    circuit_names = sorted(path.stem for path in CIRCUITS_DIR.glob("*.json"))
    return CircuitListResponse(circuits=circuit_names)


@app.post("/api/circuit/save", response_model=SaveCircuitResponse)
def save_circuit(request: SaveCircuitRequest) -> SaveCircuitResponse:
    safe_name = _validate_circuit_name(request.name)

    if _supabase_enabled():
        _save_circuit_supabase(safe_name, request.circuit)
        return SaveCircuitResponse(name=safe_name, saved=True)

    _ensure_storage_dir()
    file_path = _circuit_file_path(safe_name)
    with file_path.open("w", encoding="utf-8") as file_handle:
        json.dump(request.circuit.model_dump(), file_handle, indent=2)
    return SaveCircuitResponse(name=safe_name, saved=True)


@app.get("/api/circuit/load/{name}", response_model=SimulationRequest)
def load_circuit(name: str) -> SimulationRequest:
    if _supabase_enabled():
        circuit_data = _load_circuit_supabase(name)
        return SimulationRequest(circuit=CircuitPayload(**circuit_data))

    file_path = _circuit_file_path(name)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Circuit '{name}' not found")

    try:
        with file_path.open("r", encoding="utf-8") as file_handle:
            circuit_data = json.load(file_handle)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=500, detail="Saved circuit file is invalid"
        ) from error

    return SimulationRequest(circuit=CircuitPayload(**circuit_data))


@app.get("/api/gates/types")
def gate_types():
    return {
        "gate_types": [
            {"type": "and", "num_inputs": 2},
            {"type": "or", "num_inputs": 2},
            {"type": "not", "num_inputs": 1},
            {"type": "nand", "num_inputs": 2},
            {"type": "nor", "num_inputs": 2},
            {"type": "xor", "num_inputs": 2},
        ]
    }


@app.post("/api/gates/evaluate")
def evaluate_gate(request: GateEvaluateRequest) -> Dict[str, Optional[bool]]:
    gate = GATE_CLASSES[request.gate_type](name=request.gate_type.upper())

    if len(request.inputs) != gate.num_inputs:
        raise HTTPException(
            status_code=400,
            detail=f"{request.gate_type} gate expects {gate.num_inputs} input(s)",
        )

    for idx, value in enumerate(request.inputs):
        gate.set_input(idx, value)

    return {"output": gate.get_output()}


@app.post("/api/circuit/simulate", response_model=SimulationResponse)
def simulate_circuit(request: SimulationRequest) -> SimulationResponse:
    circuit, gates_by_id, _, outputs_by_id = _build_circuit(request.circuit)
    engine = SimulationEngine(circuit)
    engine.simulate()

    gate_outputs = {gate_id: gate.get_output() for gate_id, gate in gates_by_id.items()}
    output_values = {output_id: node.value for output_id, node in outputs_by_id.items()}

    input_names, output_names, rows = engine.generate_truth_table()
    expressions = engine.get_boolean_expression()

    return SimulationResponse(
        gate_outputs=gate_outputs,
        output_values=output_values,
        truth_table=TruthTableResponse(
            input_names=input_names,
            output_names=output_names,
            rows=rows,
        ),
        expressions=expressions,
    )


@app.get("/api/circuit/example", response_model=SimulationRequest)
def example_circuit() -> SimulationRequest:
    return SimulationRequest(
        circuit=CircuitPayload(
            inputs=[
                InputSpec(id="in_a", name="A", value=False),
                InputSpec(id="in_b", name="B", value=True),
            ],
            outputs=[OutputSpec(id="out_y", name="Y")],
            gates=[GateSpec(id="g1", type="and", name="AND1")],
            wires=[
                WireSpec(
                    source_id="in_a",
                    source_type="input",
                    target_id="g1",
                    target_type="gate",
                    target_input_index=0,
                ),
                WireSpec(
                    source_id="in_b",
                    source_type="input",
                    target_id="g1",
                    target_type="gate",
                    target_input_index=1,
                ),
                WireSpec(
                    source_id="g1",
                    source_type="gate",
                    target_id="out_y",
                    target_type="output",
                    target_input_index=0,
                ),
            ],
        )
    )
