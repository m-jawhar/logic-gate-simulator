"""
Unit Tests for Logic Gate Classes
Verifies Boolean algebra implementation
"""

import unittest
from gates import (
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
from simulation import Circuit, SimulationEngine


class TestAndGate(unittest.TestCase):
    """Test AND gate functionality"""

    def setUp(self):
        self.gate = AndGate("TestAND")

    def test_and_true_true(self):
        """1 AND 1 = 1"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, True)
        self.assertTrue(self.gate.get_output())

    def test_and_true_false(self):
        """1 AND 0 = 0"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, False)
        self.assertFalse(self.gate.get_output())

    def test_and_false_true(self):
        """0 AND 1 = 0"""
        self.gate.set_input(0, False)
        self.gate.set_input(1, True)
        self.assertFalse(self.gate.get_output())

    def test_and_false_false(self):
        """0 AND 0 = 0"""
        self.gate.set_input(0, False)
        self.gate.set_input(1, False)
        self.assertFalse(self.gate.get_output())

    def test_and_unconnected(self):
        """Unconnected inputs return None"""
        self.assertIsNone(self.gate.get_output())


class TestOrGate(unittest.TestCase):
    """Test OR gate functionality"""

    def setUp(self):
        self.gate = OrGate("TestOR")

    def test_or_true_true(self):
        """1 OR 1 = 1"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, True)
        self.assertTrue(self.gate.get_output())

    def test_or_true_false(self):
        """1 OR 0 = 1"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, False)
        self.assertTrue(self.gate.get_output())

    def test_or_false_true(self):
        """0 OR 1 = 1"""
        self.gate.set_input(0, False)
        self.gate.set_input(1, True)
        self.assertTrue(self.gate.get_output())

    def test_or_false_false(self):
        """0 OR 0 = 0"""
        self.gate.set_input(0, False)
        self.gate.set_input(1, False)
        self.assertFalse(self.gate.get_output())


class TestNotGate(unittest.TestCase):
    """Test NOT gate functionality"""

    def setUp(self):
        self.gate = NotGate("TestNOT")

    def test_not_true(self):
        """NOT 1 = 0"""
        self.gate.set_input(0, True)
        self.assertFalse(self.gate.get_output())

    def test_not_false(self):
        """NOT 0 = 1"""
        self.gate.set_input(0, False)
        self.assertTrue(self.gate.get_output())


class TestNandGate(unittest.TestCase):
    """Test NAND gate functionality"""

    def setUp(self):
        self.gate = NandGate("TestNAND")

    def test_nand_true_true(self):
        """1 NAND 1 = 0"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, True)
        self.assertFalse(self.gate.get_output())

    def test_nand_true_false(self):
        """1 NAND 0 = 1"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, False)
        self.assertTrue(self.gate.get_output())

    def test_nand_false_false(self):
        """0 NAND 0 = 1"""
        self.gate.set_input(0, False)
        self.gate.set_input(1, False)
        self.assertTrue(self.gate.get_output())


class TestNorGate(unittest.TestCase):
    """Test NOR gate functionality"""

    def setUp(self):
        self.gate = NorGate("TestNOR")

    def test_nor_true_true(self):
        """1 NOR 1 = 0"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, True)
        self.assertFalse(self.gate.get_output())

    def test_nor_false_false(self):
        """0 NOR 0 = 1"""
        self.gate.set_input(0, False)
        self.gate.set_input(1, False)
        self.assertTrue(self.gate.get_output())


class TestXorGate(unittest.TestCase):
    """Test XOR gate functionality"""

    def setUp(self):
        self.gate = XorGate("TestXOR")

    def test_xor_true_true(self):
        """1 XOR 1 = 0"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, True)
        self.assertFalse(self.gate.get_output())

    def test_xor_true_false(self):
        """1 XOR 0 = 1"""
        self.gate.set_input(0, True)
        self.gate.set_input(1, False)
        self.assertTrue(self.gate.get_output())

    def test_xor_false_true(self):
        """0 XOR 1 = 1"""
        self.gate.set_input(0, False)
        self.gate.set_input(1, True)
        self.assertTrue(self.gate.get_output())

    def test_xor_false_false(self):
        """0 XOR 0 = 0"""
        self.gate.set_input(0, False)
        self.gate.set_input(1, False)
        self.assertFalse(self.gate.get_output())


class TestCircuitSimulation(unittest.TestCase):
    """Test circuit simulation with connected components"""

    def test_simple_circuit(self):
        """Test: Input -> NOT -> Output"""
        circuit = Circuit()
        engine = SimulationEngine(circuit)

        # Create components
        inp = InputNode("A", value=True)
        out = OutputNode("Y")
        not_gate = NotGate("NOT1")

        circuit.add_input(inp)
        circuit.add_output(out)
        circuit.add_gate(not_gate)

        # Wire: Input -> NOT -> Output
        wire1 = Wire(inp, "input", not_gate, "gate", 0)
        wire2 = Wire(not_gate, "gate", out, "output", 0)
        circuit.add_wire(wire1)
        circuit.add_wire(wire2)

        # Simulate
        engine.simulate()

        # Input=1 -> NOT -> Output should be 0
        self.assertFalse(out.value)

        # Toggle input
        inp.toggle()  # Now False
        engine.simulate()

        # Input=0 -> NOT -> Output should be 1
        self.assertTrue(out.value)

    def test_and_circuit(self):
        """Test: Two inputs -> AND -> Output"""
        circuit = Circuit()
        engine = SimulationEngine(circuit)

        # Create components
        inp_a = InputNode("A", value=True)
        inp_b = InputNode("B", value=True)
        out = OutputNode("Y")
        and_gate = AndGate("AND1")

        circuit.add_input(inp_a)
        circuit.add_input(inp_b)
        circuit.add_output(out)
        circuit.add_gate(and_gate)

        # Wire connections
        wire1 = Wire(inp_a, "input", and_gate, "gate", 0)
        wire2 = Wire(inp_b, "input", and_gate, "gate", 1)
        wire3 = Wire(and_gate, "gate", out, "output", 0)
        circuit.add_wire(wire1)
        circuit.add_wire(wire2)
        circuit.add_wire(wire3)

        # Simulate with both inputs True
        engine.simulate()
        self.assertTrue(out.value)

        # Change one input to False
        inp_a.toggle()  # Now False
        engine.simulate()
        self.assertFalse(out.value)


class TestTruthTableGeneration(unittest.TestCase):
    """Test truth table generation"""

    def test_and_gate_truth_table(self):
        """Verify AND gate truth table"""
        circuit = Circuit()
        engine = SimulationEngine(circuit)

        # Create components
        inp_a = InputNode("A")
        inp_b = InputNode("B")
        out = OutputNode("Y")
        and_gate = AndGate("AND1")

        circuit.add_input(inp_a)
        circuit.add_input(inp_b)
        circuit.add_output(out)
        circuit.add_gate(and_gate)

        # Wire connections
        circuit.add_wire(Wire(inp_a, "input", and_gate, "gate", 0))
        circuit.add_wire(Wire(inp_b, "input", and_gate, "gate", 1))
        circuit.add_wire(Wire(and_gate, "gate", out, "output", 0))

        # Generate truth table
        input_names, output_names, rows = engine.generate_truth_table()

        self.assertEqual(input_names, ["A", "B"])
        self.assertEqual(output_names, ["Y"])
        self.assertEqual(len(rows), 4)  # 2^2 combinations

        # Verify AND logic: only True when both inputs are True
        expected = [
            [False, False, False],  # 0 AND 0 = 0
            [False, True, False],  # 0 AND 1 = 0
            [True, False, False],  # 1 AND 0 = 0
            [True, True, True],  # 1 AND 1 = 1
        ]
        self.assertEqual(rows, expected)


if __name__ == "__main__":
    print("Running Logic Gate Unit Tests...")
    print("=" * 50)
    unittest.main(verbosity=2)
