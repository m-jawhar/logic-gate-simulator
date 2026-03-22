"""
Logic Gate Classes - Demonstrates OOP with inheritance
Base Gate class with subclasses for AND, OR, NOT, NAND gates
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from itertools import product


class Gate(ABC):
    """Abstract base class for all logic gates"""

    def __init__(self, name: str, num_inputs: int = 2):
        self.name = name
        self.num_inputs = num_inputs
        self.inputs: List[Optional[bool]] = [None] * num_inputs
        self.output: Optional[bool] = None
        self.x = 0
        self.y = 0
        self.width = 80
        self.height = 60
        self.selected = False
        self.canvas_id = None
        self.input_wire_ids: List[Optional[int]] = [None] * num_inputs
        self.output_wire_id: Optional[int] = None

    @abstractmethod
    def compute(self) -> Optional[bool]:
        """Compute the output based on current inputs"""
        pass

    @abstractmethod
    def get_symbol(self) -> str:
        """Return the gate symbol for display"""
        pass

    def set_input(self, index: int, value: Optional[bool]) -> None:
        """Set an input value at the specified index"""
        if 0 <= index < self.num_inputs:
            self.inputs[index] = value
            self.output = self.compute()

    def get_output(self) -> Optional[bool]:
        """Get the computed output"""
        return self.output

    def get_input_position(self, index: int) -> tuple:
        """Get the canvas position for an input connector"""
        spacing = self.height / (self.num_inputs + 1)
        return (self.x, self.y + spacing * (index + 1))

    def get_output_position(self) -> tuple:
        """Get the canvas position for the output connector"""
        return (self.x + self.width, self.y + self.height / 2)

    def contains_point(self, px: int, py: int) -> bool:
        """Check if a point is inside this gate"""
        return (
            self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height
        )

    def move_to(self, x: int, y: int) -> None:
        """Move the gate to a new position"""
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', inputs={self.inputs}, output={self.output})"


class AndGate(Gate):
    """AND Gate - Output is True only if ALL inputs are True"""

    def __init__(self, name: str = "AND"):
        super().__init__(name, num_inputs=2)

    def compute(self) -> Optional[bool]:
        if None in self.inputs:
            return None
        return all(self.inputs)

    def get_symbol(self) -> str:
        return "AND"


class OrGate(Gate):
    """OR Gate - Output is True if ANY input is True"""

    def __init__(self, name: str = "OR"):
        super().__init__(name, num_inputs=2)

    def compute(self) -> Optional[bool]:
        if None in self.inputs:
            return None
        return any(self.inputs)

    def get_symbol(self) -> str:
        return "OR"


class NotGate(Gate):
    """NOT Gate (Inverter) - Output is the inverse of input"""

    def __init__(self, name: str = "NOT"):
        super().__init__(name, num_inputs=1)

    def compute(self) -> Optional[bool]:
        if self.inputs[0] is None:
            return None
        return not self.inputs[0]

    def get_symbol(self) -> str:
        return "NOT"


class NandGate(Gate):
    """NAND Gate - Output is False only if ALL inputs are True"""

    def __init__(self, name: str = "NAND"):
        super().__init__(name, num_inputs=2)

    def compute(self) -> Optional[bool]:
        if None in self.inputs:
            return None
        return not all(self.inputs)

    def get_symbol(self) -> str:
        return "NAND"


class NorGate(Gate):
    """NOR Gate - Output is True only if ALL inputs are False"""

    def __init__(self, name: str = "NOR"):
        super().__init__(name, num_inputs=2)

    def compute(self) -> Optional[bool]:
        if None in self.inputs:
            return None
        return not any(self.inputs)

    def get_symbol(self) -> str:
        return "NOR"


class XorGate(Gate):
    """XOR Gate - Output is True if inputs are different"""

    def __init__(self, name: str = "XOR"):
        super().__init__(name, num_inputs=2)

    def compute(self) -> Optional[bool]:
        if None in self.inputs:
            return None
        return self.inputs[0] != self.inputs[1]

    def get_symbol(self) -> str:
        return "XOR"


class InputNode:
    """Input node that provides a constant value to the circuit"""

    def __init__(self, name: str, value: bool = False):
        self.name = name
        self.value = value
        self.x = 0
        self.y = 0
        self.width = 50
        self.height = 40
        self.selected = False
        self.canvas_id = None
        self.output_wire_id = None

    def toggle(self) -> None:
        """Toggle the input value"""
        self.value = not self.value

    def get_output(self) -> bool:
        return self.value

    def get_output_position(self) -> tuple:
        return (self.x + self.width, self.y + self.height / 2)

    def contains_point(self, px: int, py: int) -> bool:
        return (
            self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height
        )

    def move_to(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class OutputNode:
    """Output node that displays the final result"""

    def __init__(self, name: str):
        self.name = name
        self.value: Optional[bool] = None
        self.x = 0
        self.y = 0
        self.width = 50
        self.height = 40
        self.selected = False
        self.canvas_id = None
        self.input_wire_id = None

    def set_value(self, value: Optional[bool]) -> None:
        self.value = value

    def get_input_position(self) -> tuple:
        return (self.x, self.y + self.height / 2)

    def contains_point(self, px: int, py: int) -> bool:
        return (
            self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height
        )

    def move_to(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class Wire:
    """Connection between gate outputs and inputs"""

    def __init__(
        self,
        source,
        source_type: str,
        target,
        target_type: str,
        target_input_index: int = 0,
    ):
        self.source = source  # Gate or InputNode
        self.source_type = source_type  # 'gate' or 'input'
        self.target = target  # Gate or OutputNode
        self.target_type = target_type  # 'gate' or 'output'
        self.target_input_index = target_input_index
        self.canvas_id = None

    def get_value(self) -> Optional[bool]:
        """Get the value being transmitted through this wire"""
        if self.source_type == "input":
            return self.source.get_output()
        else:
            return self.source.get_output()

    def get_start_pos(self) -> tuple:
        return self.source.get_output_position()

    def get_end_pos(self) -> tuple:
        if self.target_type == "output":
            return self.target.get_input_position()
        else:
            return self.target.get_input_position(self.target_input_index)
