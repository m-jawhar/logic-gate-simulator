# Visual Logic Gate Simulator

A graphical application for designing and simulating digital logic circuits, demonstrating the hardware-software interface from Logic System Design.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 Project Overview

This project synthesizes knowledge from **Logic System Design (B24CS1T01)** with programming skills. It translates abstract Boolean algebra into a visual, functional tool.

## ✨ Features

### 1. Canvas Area

- **Drag and Drop Interface**: Add gates by clicking in the toolbox
- **Visual Components**: AND, OR, NOT, NAND, NOR, XOR gates
- **Input/Output Nodes**: Toggle inputs and view outputs in real-time

### 2. Simulation Engine

- **Boolean Algebra Implementation**: Proper gate logic computation
- **Real-time Updates**: Outputs change immediately when inputs change
- **Value Propagation**: Signals propagate through connected wires

### 3. Truth Table Generator

- **Automatic Generation**: Creates truth table for any circuit
- **All Combinations**: Tests all possible input combinations
- **Visual Display**: Clean, formatted output

### 4. OOP Design

```
Gate (Abstract Base Class)
├── AndGate
├── OrGate
├── NotGate
├── NandGate
├── NorGate
└── XorGate
```

### 5. Unified Backend + Multi-Client Architecture

- **FastAPI backend** exposes simulation logic through HTTP APIs
- **React frontend** calls the backend from a browser
- **Tkinter desktop app** can continue running independently
- Both clients can use the same Python logic as the single source of truth

### 6. Persistent Save/Load + Interactive Web Editor

- Save circuits via API: `POST /api/circuit/save`
- List saved circuits: `GET /api/circuit/list`
- Load circuits: `GET /api/circuit/load/{name}`
- React app now mirrors the desktop layout (left toolbox, center scrollable canvas, right properties/expression/truth table)
- Web wiring uses connector-to-connector click flow in **Wire Mode** (desktop-style), not a separate wire form
- Tkinter app includes **Save To API** and **Load From API** buttons

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- Tkinter (included with Python on most systems)

### Installation

```bash
# Navigate to project directory
cd <your-project-path>/LogicGateSimulator

# Run the application
python main.py
```

### Web API + Web Frontend Setup

```bash
# 1) Install Python API dependencies
cd <your-project-path>/LogicGateSimulator
python -m pip install -r requirements.txt

# 2) Start FastAPI backend (terminal 1)
python -m uvicorn api:app --reload --port 8000

# 3) Start React frontend (terminal 2)
cd frontend
npm install
npm run dev
```

Open the frontend at `http://127.0.0.1:5173`.

### Authentication (New)

Persistence routes are now protected by bearer-token auth:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

Protected routes (require `Authorization: Bearer <token>`):

- `GET /api/circuit/list`
- `POST /api/circuit/save`
- `GET /api/circuit/load/{name}`
- `POST /api/circuit/share/{name}`

Public read-only route (no auth required):

- `GET /api/public/circuit/{share_id}`

The web app includes built-in **Register / Login / Logout** controls in the left panel and automatically sends the token for save/load/list.

### Optional Public Sharing (Read-only)

Authenticated users can create a share link for any saved circuit:

1. Save a circuit.
2. Select it in **Saved Circuits**.
3. Click **Share Selected (Read-only)**.

The generated link (`/?share=<share_id>`) loads the shared circuit for anyone with the URL.
This is read-only from a storage perspective: public users can view/simulate that shared snapshot, but they cannot overwrite your private saved circuits.

Environment variables:

```text
LOGIC_AUTH_SECRET=change-this-in-production
LOGIC_AUTH_TOKEN_TTL_SECONDS=86400
LOGIC_AUTH_HASH_ITERATIONS=200000
```

If you deploy publicly, set a strong `LOGIC_AUTH_SECRET`.

### Run Desktop and Web Together

Use separate processes to avoid event-loop blocking:

```bash
# Terminal 1: FastAPI backend
python -m uvicorn api:app --reload --port 8000

# Terminal 2: Tkinter desktop app
python main.py

# Terminal 3: React web app
cd frontend
npm run dev
```

This keeps the desktop and web clients independent while sharing the same backend logic.

### Testing

```bash
# Run all Python tests (logic + API)
cd <your-project-path>/LogicGateSimulator
python -m unittest -v

# Build-check the web frontend
cd frontend
npm run build
```

### CI on Push

GitHub Actions workflow is configured in `.github/workflows/ci.yml` to run automatically on push and pull requests:

- Python job: installs `requirements.txt` and runs `python -m unittest -v`
- Frontend job: runs `npm ci` and `npm run build` in `frontend/`

### Free Cloud Deployment (Render + Vercel)

This repository includes deployment scaffolding for a free-tier setup:

- Backend config: `render.yaml` (FastAPI on Render)
- Frontend config: `frontend/vercel.json` (Vercel rewrites for `/api/*` and `/health`)

#### 1) Deploy Backend on Render

1. Push this repo to GitHub.
2. In Render, create a new Blueprint/Web Service from the repo.
3. Render uses `render.yaml` and starts:

```bash
uvicorn api:app --host 0.0.0.0 --port $PORT
```

4. Confirm backend health:

```text
https://<your-render-backend>.onrender.com/health
```

Optional CORS override for non-default frontend hosts:

```text
LOGIC_API_CORS_ORIGINS=https://your-frontend.example.com,https://staging-frontend.example.com
```

If omitted, the API allows local development origins (`http://127.0.0.1:5173`, `http://localhost:5173`).

#### 2) Deploy Frontend on Vercel

1. In Vercel, import the same repo.
2. Set **Root Directory** to `frontend`.
3. Before deploy, edit `frontend/vercel.json` and replace:

```text
https://YOUR-RENDER-BACKEND.onrender.com
```

with your actual Render backend URL.

4. Deploy. The frontend can keep using relative API calls (e.g. `/api/circuit/simulate`).

#### 3) Free-tier persistence note

`/api/circuit/save` currently writes to local files (`data/circuits`). On many free PaaS instances, filesystem storage is ephemeral and may reset after redeploy/sleep/restart.

For durable cloud persistence, connect the save/load API to an external store (for example: free Postgres or managed key-value/object storage).

#### 4) Durable persistence with Supabase (recommended)

The API supports Supabase-backed persistence for `save/list/load` when these env vars are set:

```text
LOGIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
LOGIC_SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
LOGIC_SUPABASE_TABLE=circuits
```

Create the table in Supabase SQL Editor:

```sql
create table if not exists public.circuits (
   name text primary key,
   circuit jsonb not null,
   updated_at timestamptz not null default now()
);

create or replace function public.touch_circuits_updated_at()
returns trigger as $$
begin
   new.updated_at = now();
   return new;
end;
$$ language plpgsql;

drop trigger if exists trg_touch_circuits_updated_at on public.circuits;
create trigger trg_touch_circuits_updated_at
before update on public.circuits
for each row execute procedure public.touch_circuits_updated_at();
```

Notes:

- Use the **service role key** only on the backend (never expose in frontend).
- If Supabase vars are not set, the API automatically falls back to local file storage.

## 📖 How to Use

### Adding Components

1. Click on **"➕ Input"** to add an input node
2. Click on **"📤 Output"** to add an output node
3. Click on any gate button to add that gate

### Connecting Components

1. Click **"🔗 Wire Mode: OFF"** to enable wiring
2. Click on an **output connector** (right side of gates/inputs)
3. Click on an **input connector** (left side of gates/outputs)
4. The wire will be created automatically

### Simulating

- **Double-click** on input nodes to toggle between 0 and 1
- Outputs update automatically
- Truth table updates in the right panel

### Other Controls

- **Single-click** a component to select it (selected border is highlighted)
- **Drag** components to reposition them
- Press **Delete** to remove selected component
- Press **Escape** to cancel wiring
- Click **"🗑️ Delete Selected"** to remove selection
- Click **"🔄 Clear Circuit"** to start fresh

## 📊 Boolean Algebra Review

### Basic Gates

| Gate | Symbol | Boolean Expression | Truth Table                 |
| ---- | ------ | ------------------ | --------------------------- |
| AND  | ∧      | A ∧ B              | 1 only if both inputs are 1 |
| OR   | ∨      | A ∨ B              | 1 if any input is 1         |
| NOT  | ¬      | ¬A                 | Inverts input               |
| NAND | ⊼      | ¬(A ∧ B)           | 0 only if both inputs are 1 |
| NOR  | ⊽      | ¬(A ∨ B)           | 0 if any input is 1         |
| XOR  | ⊕      | A ⊕ B              | 1 if inputs are different   |

### Example Circuit: Half Adder

```
Input A ──┬──[AND]──────────> Carry
          │
          └──[XOR]──────────> Sum
              │
Input B ──┴──┘
```

## 🏗️ Project Structure

```
LogicGateSimulator/
├── api.py           # FastAPI backend API layer
├── main.py          # Entry point
├── gates.py         # Gate classes (OOP implementation)
├── simulation.py    # Simulation engine & truth table
├── gui.py           # Tkinter GUI implementation
├── requirements.txt # FastAPI runtime dependencies
├── frontend/        # React web frontend (Vite)
│   ├── src/
│   ├── package.json
│   └── vite.config.js
└── README.md        # This file
```

## 🎓 Educational Value

This project demonstrates:

1. **Object-Oriented Programming**
   - Abstract base classes
   - Inheritance and polymorphism
   - Encapsulation

2. **Boolean Algebra**
   - Logic gate operations
   - Truth table generation
   - Boolean expression extraction (Sum of Products)

3. **GUI Development**
   - Event-driven programming
   - Canvas-based graphics
   - User interaction handling

4. **Software Architecture**
   - Separation of concerns (MVC-like pattern)
   - Clean code organization
   - Documentation

## 📝 Future Enhancements

- [ ] Durable cloud persistence (database/object store)
- [ ] Timing diagrams
- [ ] More gate types (Buffer, XNOR)
- [ ] Circuit analysis (propagation delay)
- [ ] Custom gate creation
- [ ] Undo/Redo functionality

## 📜 License

MIT License - Feel free to use for educational purposes.

## 👨‍💻 Author

Created for Logic System Design (B24CS1T01) coursework.

---

_"The best way to understand hardware is to simulate it in software."_
