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

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- Tkinter (included with Python on most systems)

### Installation

```bash
# Navigate to project directory
cd C:\Users\Public\LogicGateSimulator

# Run the application
python main.py
```

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
├── main.py          # Entry point
├── gates.py         # Gate classes (OOP implementation)
├── simulation.py    # Simulation engine & truth table
├── gui.py           # Tkinter GUI implementation
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

- [ ] Save/Load circuits to file
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
