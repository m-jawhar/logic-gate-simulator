import { useEffect, useMemo, useRef, useState } from "react";

const GATE_INPUTS = {
  and: 2,
  or: 2,
  not: 1,
  nand: 2,
  nor: 2,
  xor: 2,
};

const NODE_SIZE = {
  input: { w: 70, h: 40 },
  output: { w: 70, h: 40 },
  gate: { w: 90, h: 60 },
};

const CANVAS_SIZE = { width: 2000, height: 2000 };
const GRID_SPACING = 20;
const MOBILE_BREAKPOINT = 980;
const MOBILE_PANES = new Set(["components", "canvas", "analysis"]);
const ANALYSIS_AUTO_COLLAPSE_ROWS = 16;

const COLORS = {
  canvasBg: "#181825",
  grid: "#313244",
  gateFill: "#45475a",
  gateOutline: "#89b4fa",
  gateText: "#cdd6f4",
  inputOn: "#a6e3a1",
  inputOff: "#f38ba8",
  outputOn: "#a6e3a1",
  outputOff: "#f38ba8",
  wire: "#89b4fa",
  wireOn: "#a6e3a1",
  wireOff: "#6c7086",
  selected: "#f9e2af",
  connector: "#cba6f7",
};

function getNodeCenter(node, kind) {
  const size = NODE_SIZE[kind];
  return { x: node.x + size.w / 2, y: node.y + size.h / 2 };
}

function getInputPort(node, kind, index = 0) {
  const size = NODE_SIZE[kind];
  if (kind === "gate") {
    const count = GATE_INPUTS[node.type] || 2;
    const spacing = size.h / (count + 1);
    return { x: node.x, y: node.y + spacing * (index + 1) };
  }
  return { x: node.x, y: node.y + size.h / 2 };
}

function getSourcePort(node, kind) {
  const size = NODE_SIZE[kind];
  return { x: node.x + size.w, y: node.y + size.h / 2 };
}

function getTargetPort(node, kind, targetInputIndex) {
  return getInputPort(node, kind, targetInputIndex);
}

function normalizeName(text) {
  return text.trim().replaceAll(/\s+/g, "_").toLowerCase();
}

function formatTruthTable(table) {
  if (!table?.rows?.length) {
    return "Run simulation to generate a truth table.";
  }

  const columns = [...table.input_names, ...table.output_names];
  const header = ` ${columns.join(" | ")} `;
  const separator = "-".repeat(header.length);
  const body = table.rows
    .map((row) => ` ${row.map((value) => (value ? "1" : "0")).join(" | ")} `)
    .join("\n");
  return `${header}\n${separator}\n${body}`;
}

function pointerToSvg(svg, clientX, clientY) {
  const point = svg.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) {
    return { x: 0, y: 0 };
  }
  const transformed = point.matrixTransform(ctm.inverse());
  return { x: transformed.x, y: transformed.y };
}

function boolToBit(value) {
  if (value === undefined || value === null) {
    return "?";
  }
  return value ? "1" : "0";
}

function valueToColor(value, unknownColor, trueColor, falseColor) {
  if (value === undefined || value === null) {
    return unknownColor;
  }
  return value ? trueColor : falseColor;
}

export default function App() {
  const [inputs, setInputs] = useState([]);
  const [gates, setGates] = useState([]);
  const [outputs, setOutputs] = useState([]);
  const [wires, setWires] = useState([]);

  const [wireMode, setWireMode] = useState(false);
  const [wireStart, setWireStart] = useState(null);
  const [previewPoint, setPreviewPoint] = useState(null);

  const [selectedNode, setSelectedNode] = useState(null);
  const [dragInfo, setDragInfo] = useState(null);

  const [simulateResult, setSimulateResult] = useState(null);
  const [showTruthModal, setShowTruthModal] = useState(false);
  const [statusMessage, setStatusMessage] = useState(
    "Ready - Drag components to canvas, click to select, wire mode to connect",
  );

  const [circuitName, setCircuitName] = useState("demo_circuit");
  const [savedCircuits, setSavedCircuits] = useState([]);
  const [selectedSavedName, setSelectedSavedName] = useState("");
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.innerWidth <= MOBILE_BREAKPOINT;
  });
  const [mobilePane, setMobilePane] = useState("canvas");
  const [analysisCollapsed, setAnalysisCollapsed] = useState({
    properties: false,
    expression: false,
  });

  const inputCounter = useRef(0);
  const outputCounter = useRef(0);
  const gateCounter = useRef(0);
  const lastAnalysisAutoLayoutRef = useRef("");
  const svgRef = useRef(null);

  const nodeById = useMemo(() => {
    const map = new Map();
    inputs.forEach((node) => map.set(node.id, { ...node, kind: "input" }));
    gates.forEach((node) => map.set(node.id, { ...node, kind: "gate" }));
    outputs.forEach((node) => map.set(node.id, { ...node, kind: "output" }));
    return map;
  }, [inputs, gates, outputs]);

  function buildCircuitPayload() {
    return {
      circuit: {
        inputs,
        outputs,
        gates,
        wires,
      },
    };
  }

  function syncCounters(nextInputs, nextOutputs, nextGates) {
    inputCounter.current = nextInputs.length;
    outputCounter.current = nextOutputs.length;
    gateCounter.current = nextGates.length;
  }

  function applyCircuitPayload(circuit) {
    const nextInputs = circuit.inputs || [];
    const nextOutputs = circuit.outputs || [];
    const nextGates = circuit.gates || [];
    const nextWires = circuit.wires || [];

    setInputs(nextInputs);
    setOutputs(nextOutputs);
    setGates(nextGates);
    setWires(nextWires);
    syncCounters(nextInputs, nextOutputs, nextGates);
    setSimulateResult(null);
    setWireStart(null);
    setPreviewPoint(null);
    setSelectedNode(null);
  }

  async function checkBackend() {
    try {
      const response = await fetch("/health");
      if (!response.ok) {
        throw new Error("health check failed");
      }
    } catch {
      setStatusMessage(
        "API offline. Start backend with: uvicorn api:app --reload --port 8000",
      );
    }
  }

  async function refreshSavedCircuits() {
    try {
      const response = await fetch("/api/circuit/list");
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Could not list saved circuits");
      }
      setSavedCircuits(data.circuits || []);
      if (!selectedSavedName && data.circuits?.length) {
        setSelectedSavedName(data.circuits[0]);
      }
      setStatusMessage("Saved circuit list refreshed.");
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  useEffect(() => {
    void checkBackend();
    void refreshSavedCircuits();
  }, []);

  useEffect(() => {
    function onResize() {
      setIsMobile(window.innerWidth <= MOBILE_BREAKPOINT);
    }

    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!isMobile && mobilePane !== "canvas") {
      setMobilePane("canvas");
    }
  }, [isMobile, mobilePane]);

  useEffect(() => {
    function syncPaneFromHash() {
      const hashPane = window.location.hash.replace("#", "");
      if (MOBILE_PANES.has(hashPane)) {
        setMobilePane(hashPane);
      }
    }

    syncPaneFromHash();
    window.addEventListener("hashchange", syncPaneFromHash);
    return () => window.removeEventListener("hashchange", syncPaneFromHash);
  }, []);

  useEffect(() => {
    if (!isMobile) {
      return;
    }

    const nextHash = `#${mobilePane}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, "", nextHash);
    }
  }, [isMobile, mobilePane]);

  useEffect(() => {
    if (!isMobile || mobilePane !== "analysis") {
      return;
    }

    const table = simulateResult?.truth_table;
    const rowCount = table?.rows?.length || 0;
    const inputCount = table?.input_names?.length || 0;
    const outputCount = table?.output_names?.length || 0;
    const signature = `${rowCount}:${inputCount}:${outputCount}`;

    if (lastAnalysisAutoLayoutRef.current === signature) {
      return;
    }

    lastAnalysisAutoLayoutRef.current = signature;
    const shouldCollapse = rowCount >= ANALYSIS_AUTO_COLLAPSE_ROWS;
    setAnalysisCollapsed({
      properties: shouldCollapse,
      expression: shouldCollapse,
    });
  }, [isMobile, mobilePane, simulateResult]);

  function totalComponentCount() {
    return inputs.length + gates.length + outputs.length;
  }

  function addInputNode() {
    inputCounter.current += 1;
    const y = 100 + totalComponentCount() * 80;
    const next = {
      id: `in_${inputCounter.current}`,
      name: `IN${inputCounter.current}`,
      value: false,
      x: 100,
      y,
    };
    setInputs((prev) => [...prev, next]);
    setStatusMessage(`Added input ${next.name}`);
    queueMicrotask(() => void simulateCircuit(false));
  }

  function addOutputNode() {
    outputCounter.current += 1;
    const y = 100 + totalComponentCount() * 80;
    const next = {
      id: `out_${outputCounter.current}`,
      name: `OUT${outputCounter.current}`,
      x: 500,
      y,
    };
    setOutputs((prev) => [...prev, next]);
    setStatusMessage(`Added output ${next.name}`);
    queueMicrotask(() => void simulateCircuit(false));
  }

  function addGate(type) {
    gateCounter.current += 1;
    const y = 100 + totalComponentCount() * 80;
    const next = {
      id: `g_${gateCounter.current}`,
      type,
      name: `${type.toUpperCase()}${gateCounter.current}`,
      x: 250,
      y,
    };
    setGates((prev) => [...prev, next]);
    setStatusMessage(`Added gate ${next.name}`);
    queueMicrotask(() => void simulateCircuit(false));
  }

  function addWireFromClick(source, target, targetInputIndex = 0) {
    const sourceType = source.kind === "input" ? "input" : "gate";
    const targetType = target.kind === "output" ? "output" : "gate";

    setWires((prev) => [
      ...prev,
      {
        source_id: source.id,
        source_type: sourceType,
        target_id: target.id,
        target_type: targetType,
        target_input_index: targetInputIndex,
      },
    ]);
    setStatusMessage("Wire connected.");
    queueMicrotask(() => void simulateCircuit(false));
  }

  function onCanvasClick() {
    setSelectedNode(null);
    if (wireMode) {
      setStatusMessage("Click on a connector to start/end wire");
    }
  }

  function onNodeClick(event, kind, node) {
    event.stopPropagation();
    if (wireMode) {
      setStatusMessage("Use connectors for wiring in wire mode.");
      return;
    }

    if (selectedNode?.id === node.id && selectedNode.kind === kind) {
      return;
    }
    setSelectedNode({ kind, id: node.id });
  }

  function onInputDoubleClick(event, node) {
    event.stopPropagation();
    if (wireMode) {
      return;
    }
    setInputs((prev) =>
      prev.map((item) =>
        item.id === node.id ? { ...item, value: !item.value } : item,
      ),
    );
    setStatusMessage(`Toggled ${node.name}`);
    queueMicrotask(() => void simulateCircuit(false));
  }

  function onConnectorClick(event, kind, node, role, inputIndex = 0) {
    event.stopPropagation();

    if (!wireMode) {
      return;
    }

    if (!wireStart) {
      const isValidStart =
        role === "output" && (kind === "input" || kind === "gate");
      if (isValidStart) {
        setWireStart({ kind, id: node.id });
        setStatusMessage(
          `Wiring from ${node.name} - click on an input connector`,
        );
      } else {
        setStatusMessage("Start wire from an OUTPUT connector");
      }
      return;
    }

    const sourceNode = nodeById.get(wireStart.id);
    const targetNode = nodeById.get(node.id);
    if (!sourceNode || !targetNode) {
      setWireStart(null);
      setPreviewPoint(null);
      return;
    }

    const isValidEnd =
      role === "input" && (kind === "gate" || kind === "output");
    if (isValidEnd) {
      const nextInputIndex =
        kind === "gate" ? Math.max(0, Number(inputIndex) || 0) : 0;
      addWireFromClick(sourceNode, targetNode, nextInputIndex);
    } else {
      setStatusMessage("End wire on an INPUT connector");
    }

    setWireStart(null);
    setPreviewPoint(null);
  }

  function onNodeMouseDown(event, kind, node) {
    if (wireMode) {
      return;
    }
    event.stopPropagation();
    const bounds = event.currentTarget.ownerSVGElement.getBoundingClientRect();
    const cursorX = event.clientX - bounds.left;
    const cursorY = event.clientY - bounds.top;
    setDragInfo({
      kind,
      id: node.id,
      offsetX: cursorX - node.x,
      offsetY: cursorY - node.y,
    });
    setSelectedNode({ kind, id: node.id });
  }

  function moveNode(kind, id, x, y) {
    const clamped = { x: Math.max(10, x), y: Math.max(10, y) };
    if (kind === "input") {
      setInputs((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...clamped } : item)),
      );
      return;
    }
    if (kind === "output") {
      setOutputs((prev) =>
        prev.map((item) => (item.id === id ? { ...item, ...clamped } : item)),
      );
      return;
    }
    setGates((prev) =>
      prev.map((item) => (item.id === id ? { ...item, ...clamped } : item)),
    );
  }

  function onCanvasMouseMove(event) {
    const svg = svgRef.current;
    if (!svg) {
      return;
    }

    const point = pointerToSvg(svg, event.clientX, event.clientY);
    if (wireMode && wireStart) {
      setPreviewPoint(point);
    }

    if (!dragInfo) {
      return;
    }
    moveNode(
      dragInfo.kind,
      dragInfo.id,
      point.x - dragInfo.offsetX,
      point.y - dragInfo.offsetY,
    );
  }

  function onCanvasMouseUp() {
    if (dragInfo) {
      setDragInfo(null);
      void simulateCircuit(false);
    }
  }

  function cancelWiring() {
    setWireStart(null);
    setPreviewPoint(null);
  }

  function toggleWireMode() {
    setWireMode((prev) => {
      const next = !prev;
      if (next) {
        setStatusMessage(
          "WIRE MODE - Click output connector, then input connector",
        );
      } else {
        setStatusMessage("Ready");
        cancelWiring();
      }
      return next;
    });
  }

  function deleteSelected() {
    if (!selectedNode) {
      setStatusMessage("Select a component before deleting.");
      return;
    }

    const { kind, id } = selectedNode;

    if (kind === "input") {
      setInputs((prev) => prev.filter((item) => item.id !== id));
      setWires((prev) => prev.filter((wire) => wire.source_id !== id));
    } else if (kind === "output") {
      setOutputs((prev) => prev.filter((item) => item.id !== id));
      setWires((prev) => prev.filter((wire) => wire.target_id !== id));
    } else {
      setGates((prev) => prev.filter((item) => item.id !== id));
      setWires((prev) =>
        prev.filter((wire) => wire.source_id !== id && wire.target_id !== id),
      );
    }

    setSelectedNode(null);
    setStatusMessage("Selected component deleted.");
    queueMicrotask(() => void simulateCircuit(false));
  }

  function clearCircuit() {
    const confirmed = globalThis.confirm(
      "Are you sure you want to clear the entire circuit?",
    );
    if (!confirmed) {
      return;
    }

    setInputs([]);
    setGates([]);
    setOutputs([]);
    setWires([]);
    setSelectedNode(null);
    cancelWiring();
    setSimulateResult(null);
    syncCounters([], [], []);
    setStatusMessage("Circuit cleared.");
  }

  async function simulateCircuit(showStatus = true) {
    if (showStatus) {
      setStatusMessage("Running simulation...");
    }

    try {
      const response = await fetch("/api/circuit/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildCircuitPayload()),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Simulation failed");
      }
      setSimulateResult(data);
      if (showStatus) {
        setStatusMessage("Simulation complete.");
      }
      return data;
    } catch (error) {
      if (showStatus) {
        setStatusMessage(error.message);
      }
      return null;
    }
  }

  async function openTruthTable() {
    let current = simulateResult;
    if (!current) {
      current = await simulateCircuit(true);
    }
    if (!current) {
      return;
    }
    setShowTruthModal(true);
  }

  async function saveCircuit() {
    const safeName = normalizeName(circuitName);
    if (!safeName) {
      setStatusMessage("Provide a circuit name before saving.");
      return;
    }

    try {
      const response = await fetch("/api/circuit/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: safeName,
          circuit: buildCircuitPayload().circuit,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Save failed");
      }
      setStatusMessage(`Saved circuit as ${data.name}`);
      setCircuitName(data.name);
      await refreshSavedCircuits();
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  async function loadCircuit() {
    if (!selectedSavedName) {
      setStatusMessage("Choose a saved circuit to load.");
      return;
    }

    try {
      const response = await fetch(
        `/api/circuit/load/${encodeURIComponent(selectedSavedName)}`,
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Load failed");
      }
      applyCircuitPayload(data.circuit);
      setStatusMessage(`Loaded ${selectedSavedName}`);
      queueMicrotask(() => void simulateCircuit(false));
    } catch (error) {
      setStatusMessage(error.message);
    }
  }

  function selectedPropertiesText() {
    if (!selectedNode) {
      return "Select a component to view properties";
    }

    const node = nodeById.get(selectedNode.id);
    if (!node) {
      return "Select a component to view properties";
    }

    if (selectedNode.kind === "gate") {
      const gateOutput = simulateResult?.gate_outputs?.[node.id];
      return [
        `Gate: ${node.type.toUpperCase()}`,
        `Name: ${node.name}`,
        `Inputs: ${GATE_INPUTS[node.type] || 2}`,
        `Output: ${boolToBit(gateOutput)}`,
        `Position: (${Math.round(node.x)}, ${Math.round(node.y)})`,
      ].join("\n");
    }

    if (selectedNode.kind === "input") {
      return [
        "Input Node",
        `Name: ${node.name}`,
        `Value: ${node.value ? "1 (HIGH)" : "0 (LOW)"}`,
        `Position: (${Math.round(node.x)}, ${Math.round(node.y)})`,
        "",
        "Double-click to toggle!",
      ].join("\n");
    }

    const outputValue = simulateResult?.output_values?.[node.id];
    return [
      "Output Node",
      `Name: ${node.name}`,
      `Value: ${boolToBit(outputValue)}`,
      `Position: (${Math.round(node.x)}, ${Math.round(node.y)})`,
    ].join("\n");
  }

  function expressionText() {
    const expressions = simulateResult?.expressions;
    if (!expressions || !Object.keys(expressions).length) {
      return "Add inputs and outputs to see expression";
    }
    return Object.entries(expressions)
      .map(([name, expr]) => `${name} = ${expr}`)
      .join("\n\n");
  }

  function toggleAnalysisSection(section) {
    setAnalysisCollapsed((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  }

  function wireStrokeColor(wire) {
    if (wire.source_type === "input") {
      const source = inputs.find((node) => node.id === wire.source_id);
      if (source) {
        return source.value ? COLORS.wireOn : COLORS.wireOff;
      }
    }

    if (wire.source_type === "gate") {
      const sourceGate = gates.find((gate) => gate.id === wire.source_id);
      if (sourceGate) {
        const value = simulateResult?.gate_outputs?.[sourceGate.id];
        if (value === true) {
          return COLORS.wireOn;
        }
        if (value === false) {
          return COLORS.wireOff;
        }
      }
    }
    return COLORS.wire;
  }

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Delete") {
        deleteSelected();
      }
      if (event.key === "Escape") {
        cancelWiring();
      }
    }

    globalThis.addEventListener("keydown", onKeyDown);
    return () => globalThis.removeEventListener("keydown", onKeyDown);
  });

  const gridLines = useMemo(() => {
    const lines = [];
    for (let i = 0; i <= CANVAS_SIZE.width; i += GRID_SPACING) {
      lines.push(
        <line
          key={`v-${i}`}
          x1={i}
          y1={0}
          x2={i}
          y2={CANVAS_SIZE.height}
          stroke={COLORS.grid}
          strokeWidth="1"
        />,
      );
    }
    for (let i = 0; i <= CANVAS_SIZE.height; i += GRID_SPACING) {
      lines.push(
        <line
          key={`h-${i}`}
          x1={0}
          y1={i}
          x2={CANVAS_SIZE.width}
          y2={i}
          stroke={COLORS.grid}
          strokeWidth="1"
        />,
      );
    }
    return lines;
  }, []);

  return (
    <div
      className={`desktop-web-root ${
        isMobile && mobilePane === "canvas"
          ? "mobile-canvas-focus"
          : isMobile && mobilePane === "analysis"
            ? "mobile-analysis-focus"
            : ""
      }`}
    >
      <div className="mobile-pane-nav">
        <button
          className={mobilePane === "components" ? "active" : ""}
          onClick={() => setMobilePane("components")}
          type="button"
        >
          Components
        </button>
        <button
          className={mobilePane === "canvas" ? "active" : ""}
          onClick={() => setMobilePane("canvas")}
          type="button"
        >
          Canvas
        </button>
        <button
          className={mobilePane === "analysis" ? "active" : ""}
          onClick={() => setMobilePane("analysis")}
          type="button"
        >
          Analysis
        </button>
      </div>

      <div className="workspace-row">
        <aside
          className={`toolbox-pane ${
            isMobile && mobilePane !== "components" ? "mobile-hidden" : ""
          }`}
        >
          <div className="toolbox-scroll">
            <h3>Components</h3>

            <h4>I/O Nodes</h4>
            <button onClick={addInputNode}>+ Input</button>
            <button onClick={addOutputNode}>Output</button>

            <hr />

            <h4>Logic Gates</h4>
            <button onClick={() => addGate("and")}>AND Gate</button>
            <button onClick={() => addGate("or")}>OR Gate</button>
            <button onClick={() => addGate("not")}>NOT Gate</button>
            <button onClick={() => addGate("nand")}>NAND Gate</button>
            <button onClick={() => addGate("nor")}>NOR Gate</button>
            <button onClick={() => addGate("xor")}>XOR Gate</button>

            <hr />

            <h4>Actions</h4>
            <button onClick={toggleWireMode}>
              Wire Mode: {wireMode ? "ON" : "OFF"}
            </button>
            <button onClick={deleteSelected}>Delete Selected</button>
            <button onClick={clearCircuit}>Clear Circuit</button>

            <hr />

            <button onClick={() => void simulateCircuit(true)}>Simulate</button>
            <button onClick={openTruthTable}>Truth Table</button>

            <hr />

            <h4>Persistence API</h4>
            <label className="mini-label" htmlFor="circuitName">
              Circuit Name
            </label>
            <input
              id="circuitName"
              value={circuitName}
              onChange={(event) => setCircuitName(event.target.value)}
            />
            <button onClick={saveCircuit}>Save To API</button>

            <label className="mini-label" htmlFor="savedCircuitSelect">
              Saved Circuits
            </label>
            <select
              id="savedCircuitSelect"
              value={selectedSavedName}
              onChange={(event) => setSelectedSavedName(event.target.value)}
            >
              <option value="">Select saved circuit</option>
              {savedCircuits.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <button onClick={loadCircuit}>Load From API</button>
            <button onClick={() => void refreshSavedCircuits()}>
              Refresh List
            </button>
          </div>
        </aside>

        <section
          className={`canvas-pane ${
            isMobile && mobilePane !== "canvas" ? "mobile-hidden" : ""
          }`}
        >
          <div className="canvas-scroll">
            <svg
              ref={svgRef}
              width={CANVAS_SIZE.width}
              height={CANVAS_SIZE.height}
              onClick={onCanvasClick}
              onMouseMove={onCanvasMouseMove}
              onMouseUp={onCanvasMouseUp}
              onMouseLeave={onCanvasMouseUp}
            >
              <rect
                x="0"
                y="0"
                width={CANVAS_SIZE.width}
                height={CANVAS_SIZE.height}
                fill={COLORS.canvasBg}
              />

              <g>{gridLines}</g>

              {wires.map((wire, index) => {
                const source = nodeById.get(wire.source_id);
                const target = nodeById.get(wire.target_id);
                if (!source || !target) {
                  return null;
                }

                const sourcePos = getSourcePort(source, source.kind);
                const targetPos = getTargetPort(
                  target,
                  target.kind,
                  wire.target_input_index,
                );
                const midX = (sourcePos.x + targetPos.x) / 2;

                return (
                  <path
                    key={`${wire.source_id}-${wire.target_id}-${index}`}
                    d={`M ${sourcePos.x} ${sourcePos.y} C ${midX} ${sourcePos.y}, ${midX} ${targetPos.y}, ${targetPos.x} ${targetPos.y}`}
                    stroke={wireStrokeColor(wire)}
                    fill="none"
                    strokeWidth="3"
                  />
                );
              })}

              {wireMode && wireStart && previewPoint
                ? (() => {
                    const startNode = nodeById.get(wireStart.id);
                    if (!startNode) {
                      return null;
                    }
                    const start = getSourcePort(startNode, startNode.kind);
                    const midX = (start.x + previewPoint.x) / 2;
                    return (
                      <path
                        d={`M ${start.x} ${start.y} C ${midX} ${start.y}, ${midX} ${previewPoint.y}, ${previewPoint.x} ${previewPoint.y}`}
                        stroke={COLORS.wire}
                        fill="none"
                        strokeWidth="2"
                        strokeDasharray="5 3"
                      />
                    );
                  })()
                : null}

              {inputs.map((node) => {
                const size = NODE_SIZE.input;
                const center = getNodeCenter(node, "input");
                const selected =
                  selectedNode?.kind === "input" &&
                  selectedNode?.id === node.id;
                const outputPos = getSourcePort(node, "input");

                return (
                  <g key={node.id}>
                    <rect
                      x={node.x}
                      y={node.y}
                      width={size.w}
                      height={size.h}
                      onClick={(event) => onNodeClick(event, "input", node)}
                      onMouseDown={(event) =>
                        onNodeMouseDown(event, "input", node)
                      }
                      onDoubleClick={(event) => onInputDoubleClick(event, node)}
                      fill={node.value ? COLORS.inputOn : COLORS.inputOff}
                      stroke={selected ? COLORS.selected : COLORS.gateOutline}
                      strokeWidth={selected ? "3" : "2"}
                      rx="3"
                    />
                    <text
                      x={center.x}
                      y={center.y - 5}
                      textAnchor="middle"
                      fill="#111827"
                      fontSize="11"
                      fontWeight="700"
                    >
                      {node.name}
                    </text>
                    <text
                      x={center.x}
                      y={center.y + 12}
                      textAnchor="middle"
                      fill="#111827"
                      fontSize="16"
                      fontWeight="700"
                    >
                      {node.value ? "1" : "0"}
                    </text>
                    <circle
                      cx={outputPos.x}
                      cy={outputPos.y}
                      r={isMobile ? "8" : "6"}
                      fill={COLORS.connector}
                      stroke="#ffffff"
                      strokeWidth={isMobile ? "1.5" : "1"}
                      onClick={(event) =>
                        onConnectorClick(event, "input", node, "output")
                      }
                    />
                  </g>
                );
              })}

              {gates.map((node) => {
                const size = NODE_SIZE.gate;
                const center = getNodeCenter(node, "gate");
                const selected =
                  selectedNode?.kind === "gate" && selectedNode?.id === node.id;
                const outputPos = getSourcePort(node, "gate");
                const gateOutput = simulateResult?.gate_outputs?.[node.id];

                return (
                  <g key={node.id}>
                    <rect
                      x={node.x}
                      y={node.y}
                      width={size.w}
                      height={size.h}
                      onClick={(event) => onNodeClick(event, "gate", node)}
                      onMouseDown={(event) =>
                        onNodeMouseDown(event, "gate", node)
                      }
                      fill={COLORS.gateFill}
                      stroke={selected ? COLORS.selected : COLORS.gateOutline}
                      strokeWidth={selected ? "3" : "2"}
                    />
                    <text
                      x={center.x}
                      y={center.y + 4}
                      textAnchor="middle"
                      fill={COLORS.gateText}
                      fontSize="24"
                      fontWeight="700"
                    >
                      {node.type.toUpperCase()}
                    </text>

                    {Array.from({ length: GATE_INPUTS[node.type] || 2 }).map(
                      (_, idx) => {
                        const pos = getInputPort(node, "gate", idx);
                        return (
                          <g key={`${node.id}-in-${idx}`}>
                            <circle
                              cx={pos.x}
                              cy={pos.y}
                              r={isMobile ? "8" : "6"}
                              fill={COLORS.connector}
                              stroke="#ffffff"
                              strokeWidth={isMobile ? "1.5" : "1"}
                              onClick={(event) =>
                                onConnectorClick(
                                  event,
                                  "gate",
                                  node,
                                  "input",
                                  idx,
                                )
                              }
                            />
                            <text
                              x={pos.x + 15}
                              y={pos.y + 3}
                              fill={COLORS.gateText}
                              fontSize="10"
                            >
                              I{idx}
                            </text>
                          </g>
                        );
                      },
                    )}

                    <circle
                      cx={outputPos.x}
                      cy={outputPos.y}
                      r={isMobile ? "8" : "6"}
                      fill={valueToColor(
                        gateOutput,
                        COLORS.connector,
                        COLORS.outputOn,
                        COLORS.outputOff,
                      )}
                      stroke="#ffffff"
                      strokeWidth={isMobile ? "1.5" : "1"}
                      onClick={(event) =>
                        onConnectorClick(event, "gate", node, "output")
                      }
                    />
                    <text
                      x={outputPos.x + 15}
                      y={outputPos.y + 4}
                      fill={COLORS.gateText}
                      fontSize="11"
                      fontWeight="700"
                    >
                      {boolToBit(gateOutput)}
                    </text>
                  </g>
                );
              })}

              {outputs.map((node) => {
                const size = NODE_SIZE.output;
                const center = getNodeCenter(node, "output");
                const selected =
                  selectedNode?.kind === "output" &&
                  selectedNode?.id === node.id;
                const inputPos = getInputPort(node, "output");
                const outputValue = simulateResult?.output_values?.[node.id];

                return (
                  <g key={node.id}>
                    <rect
                      x={node.x}
                      y={node.y}
                      width={size.w}
                      height={size.h}
                      onClick={(event) => onNodeClick(event, "output", node)}
                      onMouseDown={(event) =>
                        onNodeMouseDown(event, "output", node)
                      }
                      fill={valueToColor(
                        outputValue,
                        COLORS.gateFill,
                        COLORS.outputOn,
                        COLORS.outputOff,
                      )}
                      stroke={selected ? COLORS.selected : COLORS.gateOutline}
                      strokeWidth={selected ? "3" : "2"}
                      rx="3"
                    />
                    <text
                      x={center.x}
                      y={center.y - 5}
                      textAnchor="middle"
                      fill={outputValue == null ? COLORS.gateText : "#111827"}
                      fontSize="11"
                      fontWeight="700"
                    >
                      {node.name}
                    </text>
                    <text
                      x={center.x}
                      y={center.y + 12}
                      textAnchor="middle"
                      fill={outputValue == null ? COLORS.gateText : "#111827"}
                      fontSize="16"
                      fontWeight="700"
                    >
                      {boolToBit(outputValue)}
                    </text>
                    <circle
                      cx={inputPos.x}
                      cy={inputPos.y}
                      r={isMobile ? "8" : "6"}
                      fill={COLORS.connector}
                      stroke="#ffffff"
                      strokeWidth={isMobile ? "1.5" : "1"}
                      onClick={(event) =>
                        onConnectorClick(event, "output", node, "input", 0)
                      }
                    />
                  </g>
                );
              })}
            </svg>
          </div>
        </section>

        <aside
          className={`right-pane ${
            isMobile && mobilePane !== "analysis" ? "mobile-hidden" : ""
          }`}
        >
          <section className="panel-block">
            <div className="panel-heading">
              <h4>Properties</h4>
              {isMobile && mobilePane === "analysis" ? (
                <button
                  className="panel-toggle"
                  onClick={() => toggleAnalysisSection("properties")}
                  type="button"
                >
                  {analysisCollapsed.properties ? "Expand" : "Collapse"}
                </button>
              ) : null}
            </div>
            {!analysisCollapsed.properties ? (
              <pre>{selectedPropertiesText()}</pre>
            ) : null}
          </section>

          <section className="panel-block">
            <div className="panel-heading">
              <h4>Boolean Expression</h4>
              {isMobile && mobilePane === "analysis" ? (
                <button
                  className="panel-toggle"
                  onClick={() => toggleAnalysisSection("expression")}
                  type="button"
                >
                  {analysisCollapsed.expression ? "Expand" : "Collapse"}
                </button>
              ) : null}
            </div>
            {!analysisCollapsed.expression ? (
              <pre>{expressionText()}</pre>
            ) : null}
          </section>

          <section className="panel-block panel-truth">
            <h4>Truth Table</h4>
            <div className="truth-table-scroll">
              <pre>{formatTruthTable(simulateResult?.truth_table)}</pre>
            </div>
          </section>
        </aside>
      </div>

      <div className="status-bar">{statusMessage}</div>

      {showTruthModal ? (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Truth Table</h3>
              <button onClick={() => setShowTruthModal(false)}>Close</button>
            </div>
            <pre className="truth-modal-pre">
              {formatTruthTable(simulateResult?.truth_table)}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}
