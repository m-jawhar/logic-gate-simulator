"""
Visual Logic Gate Simulator
===========================

A graphical application for designing and simulating digital logic circuits.

Features:
- Drag and drop logic gates (AND, OR, NOT, NAND, NOR, XOR)
- Connect gates with wires
- Real-time simulation
- Automatic truth table generation
- Boolean expression extraction

Author: Logic System Design Project
Course: B24CS1T01 - Logic System Design

Usage:
    python main.py

Controls:
    - Click components in toolbox to add to canvas
    - Drag components to reposition
    - Double-click input nodes to toggle (0/1)
    - Enable "Wire Mode" to connect outputs to inputs
    - Press Delete to remove selected component
    - Press Escape to cancel wiring

OOP Design Pattern:
    - Base class: Gate (abstract)
    - Subclasses: AndGate, OrGate, NotGate, NandGate, NorGate, XorGate
    - Demonstrates inheritance and polymorphism
"""

from gui import main

if __name__ == "__main__":
    print("=" * 50)
    print("  Visual Logic Gate Simulator")
    print("  Logic System Design Project")
    print("=" * 50)
    print()
    print("Starting application...")
    print()
    print("Tips:")
    print("  • Add Input/Output nodes first")
    print("  • Add gates from the toolbox")
    print("  • Single-click a component to select it")
    print("  • Use Wire Mode to connect components")
    print("  • Double-click inputs to toggle value")
    print("  • Truth table updates automatically")
    print()
    main()
