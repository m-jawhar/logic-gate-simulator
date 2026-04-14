"""
FastAPI backend for the Logic Gate Simulator.

This module exposes the existing simulation engine through HTTP APIs so
multiple clients (Tkinter desktop app, React web app, etc.) can share the
same backend logic.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, cast

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
    type: str = Field(
        ...,
        description="Built-in gate type or custom gate type in form custom:<name>",
    )
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
    rows: List[List[Optional[bool]]]


class SimulationResponse(BaseModel):
    gate_outputs: Dict[str, Optional[bool]]
    output_values: Dict[str, Optional[bool]]
    truth_table: TruthTableResponse
    expressions: Dict[str, str]


class TimingSignal(BaseModel):
    name: str
    values: List[Optional[bool]]


class TimingResponse(BaseModel):
    steps: List[int]
    signals: List[TimingSignal]


class AuthCredentials(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class AuthMeResponse(BaseModel):
    username: str


class ShareCircuitResponse(BaseModel):
    share_id: str
    share_path: str


class CreateCustomGateRequest(BaseModel):
    name: str
    circuit: CircuitPayload
    output_name: Optional[str] = None


class CustomGateDefinition(BaseModel):
    name: str
    input_names: List[str]
    expression: str


class CustomGateListResponse(BaseModel):
    gates: List[CustomGateDefinition]


class ShareCustomGateResponse(BaseModel):
    share_id: str
    share_path: str
    gate: CustomGateDefinition


class ImportCustomGateRequest(BaseModel):
    name: Optional[str] = None


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
PUBLIC_CIRCUITS_DIR = PROJECT_DIR / "data" / "public_circuits"
USERS_FILE = PROJECT_DIR / "data" / "users.json"
CUSTOM_GATES_FILE = PROJECT_DIR / "data" / "custom_gates.json"
PUBLIC_CUSTOM_GATES_FILE = PROJECT_DIR / "data" / "public_custom_gates.json"
VALID_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
VALID_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPABASE_URL = os.environ.get("LOGIC_SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("LOGIC_SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TABLE = os.environ.get("LOGIC_SUPABASE_TABLE", "circuits")
SUPABASE_USERS_TABLE = os.environ.get("LOGIC_SUPABASE_USERS_TABLE", "logic_users")
SUPABASE_CUSTOM_GATES_TABLE = os.environ.get(
    "LOGIC_SUPABASE_CUSTOM_GATES_TABLE", "custom_gates"
)
SUPABASE_PUBLIC_CUSTOM_GATES_TABLE = os.environ.get(
    "LOGIC_SUPABASE_PUBLIC_CUSTOM_GATES_TABLE", "public_custom_gates"
)
SUPABASE_TIMEOUT_SECONDS = 8.0
AUTH_SECRET = os.environ.get("LOGIC_AUTH_SECRET", "change-me-dev-secret")
AUTH_TOKEN_TTL_SECONDS = int(os.environ.get("LOGIC_AUTH_TOKEN_TTL_SECONDS", "86400"))
PASSWORD_HASH_ITERATIONS = int(os.environ.get("LOGIC_AUTH_HASH_ITERATIONS", "200000"))

auth_scheme = HTTPBearer(auto_error=False)


class CustomExpressionGate(Gate):
    def __init__(self, name: str, input_names: List[str], expression: str):
        super().__init__(name, num_inputs=len(input_names))
        self.input_names = input_names
        self.expression = expression

    def get_symbol(self) -> str:
        return self.name

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
            evaluated = eval(normalized, {"__builtins__": {}}, context)
        except Exception as error:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid custom gate expression for {self.name}: {error}",
            ) from error

        return bool(evaluated)


def _supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _supabase_base_url() -> str:
    return f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"


def _supabase_table_url(table_name: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table_name}"


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


def _ensure_users_file() -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}", encoding="utf-8")


def _load_users() -> Dict[str, Dict[str, str]]:
    _ensure_users_file()
    try:
        raw = USERS_FILE.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=500, detail="User store is invalid") from error

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail="User store is invalid")

    users: Dict[str, Dict[str, str]] = {}
    for username, profile in parsed.items():
        if not isinstance(username, str) or not isinstance(profile, dict):
            continue
        salt = profile.get("salt")
        password_hash = profile.get("password_hash")
        if isinstance(salt, str) and isinstance(password_hash, str):
            users[username] = {"salt": salt, "password_hash": password_hash}
    return users


def _save_users(users: Dict[str, Dict[str, str]]) -> None:
    _ensure_users_file()
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _get_user_profile(username: str) -> Optional[Dict[str, str]]:
    if _supabase_enabled():
        try:
            with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
                response = client.get(
                    _supabase_table_url(SUPABASE_USERS_TABLE),
                    params={
                        "select": "username,salt,password_hash",
                        "username": f"eq.{username}",
                        "limit": "1",
                    },
                    headers=_supabase_headers(),
                )
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase user lookup failed: {error}",
            ) from error

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase user lookup failed: {response.text}",
            )

        rows = response.json()
        if not rows:
            return None

        row = rows[0]
        if not isinstance(row, dict):
            return None
        username_value = row.get("username")
        salt = row.get("salt")
        password_hash = row.get("password_hash")
        if (
            isinstance(username_value, str)
            and isinstance(salt, str)
            and isinstance(password_hash, str)
        ):
            return {
                "username": username_value,
                "salt": salt,
                "password_hash": password_hash,
            }
        return None

    users = _load_users()
    profile = users.get(username)
    if not profile:
        return None
    return {
        "username": username,
        "salt": profile["salt"],
        "password_hash": profile["password_hash"],
    }


def _user_exists(username: str) -> bool:
    return _get_user_profile(username) is not None


def _ensure_custom_gates_file() -> None:
    CUSTOM_GATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CUSTOM_GATES_FILE.exists():
        CUSTOM_GATES_FILE.write_text("{}", encoding="utf-8")


def _ensure_public_custom_gates_file() -> None:
    PUBLIC_CUSTOM_GATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not PUBLIC_CUSTOM_GATES_FILE.exists():
        PUBLIC_CUSTOM_GATES_FILE.write_text("{}", encoding="utf-8")


def _load_custom_gate_store() -> Dict[str, Dict[str, Dict[str, object]]]:
    _ensure_custom_gates_file()
    try:
        raw = CUSTOM_GATES_FILE.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=500,
            detail="Custom gate store is invalid",
        ) from error

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail="Custom gate store is invalid")
    return cast(Dict[str, Dict[str, Dict[str, object]]], parsed)


def _save_custom_gate_store(store: Dict[str, Dict[str, Dict[str, object]]]) -> None:
    _ensure_custom_gates_file()
    CUSTOM_GATES_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _load_public_custom_gate_store() -> Dict[str, Dict[str, object]]:
    _ensure_public_custom_gates_file()
    try:
        raw = PUBLIC_CUSTOM_GATES_FILE.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=500,
            detail="Public custom gate store is invalid",
        ) from error

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=500,
            detail="Public custom gate store is invalid",
        )

    return cast(Dict[str, Dict[str, object]], parsed)


def _save_public_custom_gate_store(store: Dict[str, Dict[str, object]]) -> None:
    _ensure_public_custom_gates_file()
    PUBLIC_CUSTOM_GATES_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _validate_symbol_name(name: str, label: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{label} cannot be empty")
    if not VALID_SYMBOL.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"{label} must match [A-Za-z_][A-Za-z0-9_]*",
        )
    return normalized


def _list_custom_gates_for_user(username: str) -> List[CustomGateDefinition]:
    if _supabase_enabled():
        try:
            with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
                response = client.get(
                    _supabase_table_url(SUPABASE_CUSTOM_GATES_TABLE),
                    params={
                        "select": "name,input_names,expression",
                        "username": f"eq.{username}",
                        "order": "name.asc",
                    },
                    headers=_supabase_headers(),
                )
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase custom gate list failed: {error}",
            ) from error

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase custom gate list failed: {response.text}",
            )

        gates: List[CustomGateDefinition] = []
        for row in response.json():
            if not isinstance(row, dict):
                continue
            gate_name = row.get("name")
            expression = row.get("expression")
            input_names = row.get("input_names")
            if (
                isinstance(gate_name, str)
                and isinstance(expression, str)
                and isinstance(input_names, list)
                and all(isinstance(item, str) for item in input_names)
            ):
                gates.append(
                    CustomGateDefinition(
                        name=gate_name,
                        input_names=[item for item in input_names if item.strip()],
                        expression=expression,
                    )
                )
        return gates

    store = _load_custom_gate_store()
    user_gates = store.get(username, {})
    gates: List[CustomGateDefinition] = []

    for gate_name in sorted(user_gates.keys()):
        gate_def = user_gates[gate_name]
        input_names = gate_def.get("input_names")
        expression = gate_def.get("expression")
        if not isinstance(input_names, list) or not isinstance(expression, str):
            continue
        safe_input_names = [
            item for item in input_names if isinstance(item, str) and item.strip()
        ]
        gates.append(
            CustomGateDefinition(
                name=gate_name,
                input_names=safe_input_names,
                expression=expression,
            )
        )

    return gates


def _get_custom_gate_for_user(
    username: str, gate_name: str
) -> Optional[CustomGateDefinition]:
    safe_gate_name = _validate_symbol_name(gate_name, "Custom gate name")

    if _supabase_enabled():
        try:
            with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
                response = client.get(
                    _supabase_table_url(SUPABASE_CUSTOM_GATES_TABLE),
                    params={
                        "select": "name,input_names,expression",
                        "username": f"eq.{username}",
                        "name": f"eq.{safe_gate_name}",
                        "limit": "1",
                    },
                    headers=_supabase_headers(),
                )
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase custom gate lookup failed: {error}",
            ) from error

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase custom gate lookup failed: {response.text}",
            )

        rows = response.json()
        if not rows:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            return None
        input_names = row.get("input_names")
        expression = row.get("expression")
        if not isinstance(input_names, list) or not isinstance(expression, str):
            return None
        if not all(isinstance(item, str) for item in input_names):
            return None
        return CustomGateDefinition(
            name=safe_gate_name,
            input_names=[item for item in input_names if item.strip()],
            expression=expression,
        )

    gates = _list_custom_gates_for_user(username)
    for gate in gates:
        if gate.name == safe_gate_name:
            return gate
    return None


def _save_custom_gate_for_user(
    username: str,
    gate: CustomGateDefinition,
    *,
    overwrite: bool,
) -> None:
    if _supabase_enabled():
        params = {"on_conflict": "username,name"} if overwrite else None
        prefer = (
            "resolution=merge-duplicates,return=minimal"
            if overwrite
            else "return=minimal"
        )
        payload = [
            {
                "username": username,
                "name": gate.name,
                "input_names": gate.input_names,
                "expression": gate.expression,
            }
        ]
        try:
            with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
                response = client.post(
                    _supabase_table_url(SUPABASE_CUSTOM_GATES_TABLE),
                    params=params,
                    headers=_supabase_headers(prefer=prefer),
                    json=payload,
                )
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase custom gate save failed: {error}",
            ) from error

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase custom gate save failed: {response.text}",
            )
        return

    store = _load_custom_gate_store()
    user_gates = store.get(username, {})
    if not overwrite and gate.name in user_gates:
        raise HTTPException(
            status_code=409,
            detail=f"Custom gate '{gate.name}' already exists",
        )

    user_gates[gate.name] = {
        "input_names": gate.input_names,
        "expression": gate.expression,
    }
    store[username] = user_gates
    _save_custom_gate_store(store)


def _new_custom_gate_share_id() -> str:
    return f"sg_{secrets.token_hex(6)}"


def _get_shared_custom_gate(share_id: str) -> CustomGateDefinition:
    safe_share_id = _validate_circuit_name(share_id)

    if _supabase_enabled():
        try:
            with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
                response = client.get(
                    _supabase_table_url(SUPABASE_PUBLIC_CUSTOM_GATES_TABLE),
                    params={
                        "select": "name,input_names,expression",
                        "share_id": f"eq.{safe_share_id}",
                        "limit": "1",
                    },
                    headers=_supabase_headers(),
                )
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase shared custom gate lookup failed: {error}",
            ) from error

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase shared custom gate lookup failed: {response.text}",
            )

        rows = response.json()
        if not rows:
            raise HTTPException(status_code=404, detail="Shared custom gate not found")

        row = rows[0]
        if not isinstance(row, dict):
            raise HTTPException(status_code=500, detail="Shared custom gate is invalid")

        gate_name = row.get("name")
        input_names = row.get("input_names")
        expression = row.get("expression")
        if (
            not isinstance(gate_name, str)
            or not isinstance(expression, str)
            or not isinstance(input_names, list)
            or not all(isinstance(item, str) and item.strip() for item in input_names)
        ):
            raise HTTPException(status_code=500, detail="Shared custom gate is invalid")

        return CustomGateDefinition(
            name=gate_name,
            input_names=[item for item in input_names if isinstance(item, str)],
            expression=expression,
        )

    store = _load_public_custom_gate_store()
    entry = store.get(safe_share_id)
    if not isinstance(entry, dict):
        raise HTTPException(status_code=404, detail="Shared custom gate not found")

    gate_name = entry.get("name")
    input_names = entry.get("input_names")
    expression = entry.get("expression")
    if not isinstance(gate_name, str) or not isinstance(expression, str):
        raise HTTPException(status_code=500, detail="Shared custom gate is invalid")
    if not isinstance(input_names, list) or not all(
        isinstance(item, str) and item.strip() for item in input_names
    ):
        raise HTTPException(status_code=500, detail="Shared custom gate is invalid")

    return CustomGateDefinition(
        name=gate_name,
        input_names=[item for item in input_names if isinstance(item, str)],
        expression=expression,
    )


def _save_shared_custom_gate(
    share_id: str,
    gate: CustomGateDefinition,
    owner: str,
) -> None:
    safe_share_id = _validate_circuit_name(share_id)
    if _supabase_enabled():
        payload = [
            {
                "share_id": safe_share_id,
                "name": gate.name,
                "input_names": gate.input_names,
                "expression": gate.expression,
                "owner": owner,
            }
        ]
        try:
            with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
                response = client.post(
                    _supabase_table_url(SUPABASE_PUBLIC_CUSTOM_GATES_TABLE),
                    headers=_supabase_headers(prefer="return=minimal"),
                    json=payload,
                )
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase shared custom gate save failed: {error}",
            ) from error

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase shared custom gate save failed: {response.text}",
            )
        return

    store = _load_public_custom_gate_store()
    store[safe_share_id] = {
        "name": gate.name,
        "input_names": gate.input_names,
        "expression": gate.expression,
        "owner": owner,
    }
    _save_public_custom_gate_store(store)


def _validate_username(username: str) -> str:
    normalized = username.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    if not VALID_NAME.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail="Username must match [A-Za-z0-9_-]",
        )
    if len(normalized) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 chars")
    return normalized


def _validate_password(password: str) -> str:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 chars")
    return password


def _hash_password(password: str, salt: str) -> str:
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PASSWORD_HASH_ITERATIONS,
    )
    return hashed.hex()


def _create_user(username: str, password: str) -> None:
    normalized = _validate_username(username)
    secret = _validate_password(password)
    if _user_exists(normalized):
        raise HTTPException(status_code=409, detail="Username already exists")

    salt = secrets.token_hex(16)
    password_hash = _hash_password(secret, salt)

    if _supabase_enabled():
        payload = [
            {
                "username": normalized,
                "salt": salt,
                "password_hash": password_hash,
            }
        ]
        try:
            with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
                response = client.post(
                    _supabase_table_url(SUPABASE_USERS_TABLE),
                    headers=_supabase_headers(prefer="return=minimal"),
                    json=payload,
                )
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase user create failed: {error}",
            ) from error

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Supabase user create failed: {response.text}",
            )
        return

    users = _load_users()
    users[normalized] = {
        "salt": salt,
        "password_hash": password_hash,
    }
    _save_users(users)


def _verify_user_credentials(username: str, password: str) -> bool:
    normalized = _validate_username(username)
    profile = _get_user_profile(normalized)
    if not profile:
        return False

    candidate_hash = _hash_password(password, profile["salt"])
    return hmac.compare_digest(candidate_hash, profile["password_hash"])


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _create_auth_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": int(time.time()) + AUTH_TOKEN_TTL_SECONDS,
    }
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def _verify_auth_token(token: str) -> str:
    try:
        payload_b64, provided_signature = token.split(".", 1)
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Invalid auth token") from error

    expected_signature = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, provided_signature):
        raise HTTPException(status_code=401, detail="Invalid auth token")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=401, detail="Invalid auth token") from error

    username = payload.get("sub")
    exp = payload.get("exp")
    if not isinstance(username, str) or not isinstance(exp, int):
        raise HTTPException(status_code=401, detail="Invalid auth token")
    if exp < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired")

    if not _user_exists(username):
        raise HTTPException(status_code=401, detail="Invalid auth token")
    return username


def _require_authenticated_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return _verify_auth_token(credentials.credentials)


def _resolve_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
) -> Optional[str]:
    if credentials is None:
        return None
    return _verify_auth_token(credentials.credentials)


def _scoped_circuit_name(username: str, name: str) -> str:
    return f"{username}::{_validate_circuit_name(name)}"


def _display_name_from_scoped(username: str, scoped_name: str) -> Optional[str]:
    prefix = f"{username}::"
    if not scoped_name.startswith(prefix):
        return None
    return scoped_name[len(prefix) :]


def _public_scoped_circuit_name(share_id: str) -> str:
    safe_share_id = _validate_circuit_name(share_id)
    return f"public::{safe_share_id}"


def _new_share_id() -> str:
    return f"sh_{secrets.token_hex(6)}"


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


def _user_circuit_file_path(username: str, name: str) -> Path:
    safe_name = _validate_circuit_name(name)
    return CIRCUITS_DIR / username / f"{safe_name}.json"


def _public_circuit_file_path(share_id: str) -> Path:
    safe_share_id = _validate_circuit_name(share_id)
    return PUBLIC_CIRCUITS_DIR / f"{safe_share_id}.json"


def _list_saved_circuits_supabase(username: str) -> List[str]:
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
    circuit_names: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_name = row.get("name")
        if not isinstance(raw_name, str):
            continue
        display_name = _display_name_from_scoped(username, raw_name)
        if display_name:
            circuit_names.append(display_name)
    return sorted(circuit_names)


def _save_circuit_supabase(
    username: str, name: str, circuit_payload: CircuitPayload
) -> None:
    scoped_name = _scoped_circuit_name(username, name)
    payload = [{"name": scoped_name, "circuit": circuit_payload.model_dump()}]

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


def _load_circuit_supabase(username: str, name: str) -> Dict[str, object]:
    safe_name = _validate_circuit_name(name)
    scoped_name = _scoped_circuit_name(username, safe_name)

    try:
        with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
            response = client.get(
                _supabase_base_url(),
                params={"select": "circuit", "name": f"eq.{scoped_name}", "limit": "1"},
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


def _save_public_circuit_supabase(
    share_id: str, circuit_payload: CircuitPayload
) -> None:
    scoped_name = _public_scoped_circuit_name(share_id)
    payload = [{"name": scoped_name, "circuit": circuit_payload.model_dump()}]

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
            detail=f"Supabase public share failed: {error}",
        ) from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase public share failed: {response.text}",
        )


def _load_public_circuit_supabase(share_id: str) -> Dict[str, object]:
    scoped_name = _public_scoped_circuit_name(share_id)

    try:
        with httpx.Client(timeout=SUPABASE_TIMEOUT_SECONDS) as client:
            response = client.get(
                _supabase_base_url(),
                params={"select": "circuit", "name": f"eq.{scoped_name}", "limit": "1"},
                headers=_supabase_headers(),
            )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase public load failed: {error}",
        ) from error

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Supabase public load failed: {response.text}",
        )

    rows = response.json()
    if not rows:
        raise HTTPException(status_code=404, detail="Shared circuit not found")

    circuit_data = rows[0].get("circuit")
    if not isinstance(circuit_data, dict):
        raise HTTPException(status_code=500, detail="Shared circuit payload is invalid")
    return circuit_data


def _build_circuit(
    payload: CircuitPayload,
    username: Optional[str] = None,
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
        gate_name = gate_spec.name or gate_spec.id.upper()
        if gate_spec.type in GATE_CLASSES:
            gate_class = GATE_CLASSES[gate_spec.type]
            gate = gate_class(gate_name)
        elif gate_spec.type.startswith("custom:"):
            if not username:
                raise HTTPException(
                    status_code=401,
                    detail="Custom gates require authentication",
                )
            custom_name = gate_spec.type.split(":", 1)[1]
            gate_def = _get_custom_gate_for_user(username, custom_name)
            if gate_def is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown custom gate: {custom_name}",
                )
            gate = CustomExpressionGate(
                gate_name,
                gate_def.input_names,
                gate_def.expression,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported gate type: {gate_spec.type}",
            )
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


@app.post("/api/auth/register", response_model=AuthResponse)
def register(credentials: AuthCredentials) -> AuthResponse:
    username = _validate_username(credentials.username)
    _create_user(username, credentials.password)
    return AuthResponse(access_token=_create_auth_token(username), username=username)


@app.post("/api/auth/login", response_model=AuthResponse)
def login(credentials: AuthCredentials) -> AuthResponse:
    username = _validate_username(credentials.username)
    if not _verify_user_credentials(username, credentials.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return AuthResponse(access_token=_create_auth_token(username), username=username)


@app.get("/api/auth/me", response_model=AuthMeResponse)
def auth_me(username: str = Depends(_require_authenticated_user)) -> AuthMeResponse:
    return AuthMeResponse(username=username)


@app.get("/api/storage/info")
def storage_info() -> Dict[str, str]:
    return {
        "mode": "supabase" if _supabase_enabled() else "filesystem",
        "table": SUPABASE_TABLE if _supabase_enabled() else "data/circuits",
        "auth_store": (
            SUPABASE_USERS_TABLE if _supabase_enabled() else "data/users.json"
        ),
        "custom_gate_store": (
            SUPABASE_CUSTOM_GATES_TABLE
            if _supabase_enabled()
            else "data/custom_gates.json"
        ),
        "public_custom_gate_store": (
            SUPABASE_PUBLIC_CUSTOM_GATES_TABLE
            if _supabase_enabled()
            else "data/public_custom_gates.json"
        ),
    }


@app.get("/api/custom-gates", response_model=CustomGateListResponse)
def list_custom_gates(
    username: str = Depends(_require_authenticated_user),
) -> CustomGateListResponse:
    return CustomGateListResponse(gates=_list_custom_gates_for_user(username))


@app.post("/api/custom-gates/create", response_model=CustomGateDefinition)
def create_custom_gate(
    request: CreateCustomGateRequest,
    username: str = Depends(_require_authenticated_user),
) -> CustomGateDefinition:
    gate_name = _validate_symbol_name(request.name.lower(), "Custom gate name")
    circuit, _, _, _ = _build_circuit(request.circuit, username=username)
    engine = SimulationEngine(circuit)
    expressions = engine.get_boolean_expression()

    if not expressions:
        raise HTTPException(
            status_code=400,
            detail="Circuit must include inputs and at least one output",
        )

    output_name = request.output_name or next(iter(expressions.keys()))
    if output_name not in expressions:
        raise HTTPException(
            status_code=400,
            detail=f"Output '{output_name}' not found in expression results",
        )

    input_names = [
        _validate_symbol_name(node.name, "Input name")
        for node in request.circuit.inputs
    ]
    if not input_names:
        raise HTTPException(
            status_code=400,
            detail="Custom gate circuit must include at least one input",
        )

    gate_definition = CustomGateDefinition(
        name=gate_name,
        input_names=input_names,
        expression=expressions[output_name],
    )
    _save_custom_gate_for_user(username, gate_definition, overwrite=True)

    return gate_definition


@app.post("/api/custom-gates/share/{name}", response_model=ShareCustomGateResponse)
def share_custom_gate(
    name: str,
    username: str = Depends(_require_authenticated_user),
) -> ShareCustomGateResponse:
    safe_gate_name = _validate_symbol_name(name.lower(), "Custom gate name")
    gate = _get_custom_gate_for_user(username, safe_gate_name)
    if gate is None:
        raise HTTPException(
            status_code=404, detail=f"Custom gate '{safe_gate_name}' not found"
        )

    share_id = _new_custom_gate_share_id()
    _save_shared_custom_gate(share_id, gate, username)

    return ShareCustomGateResponse(
        share_id=share_id,
        share_path=f"/?gateShare={share_id}",
        gate=gate,
    )


@app.get("/api/public/custom-gates/{share_id}", response_model=CustomGateDefinition)
def get_public_shared_custom_gate(share_id: str) -> CustomGateDefinition:
    return _get_shared_custom_gate(share_id)


@app.post("/api/custom-gates/import/{share_id}", response_model=CustomGateDefinition)
def import_shared_custom_gate(
    share_id: str,
    request: ImportCustomGateRequest,
    username: str = Depends(_require_authenticated_user),
) -> CustomGateDefinition:
    shared_gate = _get_shared_custom_gate(share_id)
    target_name = (
        _validate_symbol_name(request.name.lower(), "Custom gate name")
        if request.name
        else shared_gate.name
    )

    if _get_custom_gate_for_user(username, target_name) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Custom gate '{target_name}' already exists",
        )

    imported_gate = CustomGateDefinition(
        name=target_name,
        input_names=shared_gate.input_names,
        expression=shared_gate.expression,
    )
    _save_custom_gate_for_user(username, imported_gate, overwrite=False)

    return imported_gate


@app.get("/api/circuit/list", response_model=CircuitListResponse)
def list_saved_circuits(
    username: str = Depends(_require_authenticated_user),
) -> CircuitListResponse:
    if _supabase_enabled():
        return CircuitListResponse(circuits=_list_saved_circuits_supabase(username))

    user_dir = CIRCUITS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    circuit_names = sorted(path.stem for path in user_dir.glob("*.json"))
    return CircuitListResponse(circuits=circuit_names)


@app.post("/api/circuit/save", response_model=SaveCircuitResponse)
def save_circuit(
    request: SaveCircuitRequest,
    username: str = Depends(_require_authenticated_user),
) -> SaveCircuitResponse:
    safe_name = _validate_circuit_name(request.name)

    if _supabase_enabled():
        _save_circuit_supabase(username, safe_name, request.circuit)
        return SaveCircuitResponse(name=safe_name, saved=True)

    file_path = _user_circuit_file_path(username, safe_name)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as file_handle:
        json.dump(request.circuit.model_dump(), file_handle, indent=2)
    return SaveCircuitResponse(name=safe_name, saved=True)


@app.get("/api/circuit/load/{name}", response_model=SimulationRequest)
def load_circuit(
    name: str,
    username: str = Depends(_require_authenticated_user),
) -> SimulationRequest:
    if _supabase_enabled():
        circuit_data = _load_circuit_supabase(username, name)
        return SimulationRequest(circuit=CircuitPayload(**circuit_data))

    file_path = _user_circuit_file_path(username, name)
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


@app.post("/api/circuit/share/{name}", response_model=ShareCircuitResponse)
def share_circuit(
    name: str,
    username: str = Depends(_require_authenticated_user),
) -> ShareCircuitResponse:
    safe_name = _validate_circuit_name(name)
    share_id = _new_share_id()

    if _supabase_enabled():
        source_circuit = _load_circuit_supabase(username, safe_name)
        _save_public_circuit_supabase(share_id, CircuitPayload(**source_circuit))
        return ShareCircuitResponse(
            share_id=share_id,
            share_path=f"/?share={share_id}",
        )

    source_file = _user_circuit_file_path(username, safe_name)
    if not source_file.exists():
        raise HTTPException(status_code=404, detail=f"Circuit '{safe_name}' not found")

    try:
        with source_file.open("r", encoding="utf-8") as file_handle:
            circuit_data = json.load(file_handle)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=500, detail="Saved circuit file is invalid"
        ) from error

    PUBLIC_CIRCUITS_DIR.mkdir(parents=True, exist_ok=True)
    public_file = _public_circuit_file_path(share_id)
    with public_file.open("w", encoding="utf-8") as file_handle:
        json.dump(circuit_data, file_handle, indent=2)

    return ShareCircuitResponse(
        share_id=share_id,
        share_path=f"/?share={share_id}",
    )


@app.get("/api/public/circuit/{share_id}", response_model=SimulationRequest)
def load_public_shared_circuit(share_id: str) -> SimulationRequest:
    safe_share_id = _validate_circuit_name(share_id)

    if _supabase_enabled():
        circuit_data = _load_public_circuit_supabase(safe_share_id)
        return SimulationRequest(circuit=CircuitPayload(**circuit_data))

    public_file = _public_circuit_file_path(safe_share_id)
    if not public_file.exists():
        raise HTTPException(status_code=404, detail="Shared circuit not found")

    try:
        with public_file.open("r", encoding="utf-8") as file_handle:
            circuit_data = json.load(file_handle)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=500, detail="Shared circuit payload is invalid"
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
def simulate_circuit(
    request: SimulationRequest,
    username: Optional[str] = Depends(_resolve_optional_user),
) -> SimulationResponse:
    circuit, gates_by_id, _, outputs_by_id = _build_circuit(
        request.circuit,
        username=username,
    )
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


@app.post("/api/circuit/timing", response_model=TimingResponse)
def timing_diagram(
    request: SimulationRequest,
    username: Optional[str] = Depends(_resolve_optional_user),
) -> TimingResponse:
    circuit, _, _, _ = _build_circuit(request.circuit, username=username)
    engine = SimulationEngine(circuit)
    input_names, output_names, rows = engine.generate_truth_table()

    if not rows:
        return TimingResponse(steps=[], signals=[])

    step_count = len(rows)
    steps = list(range(step_count))
    signal_names = input_names + output_names
    signals: List[TimingSignal] = []
    for signal_index, signal_name in enumerate(signal_names):
        values = [row[signal_index] for row in rows]
        signals.append(TimingSignal(name=signal_name, values=values))

    return TimingResponse(steps=steps, signals=signals)


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
