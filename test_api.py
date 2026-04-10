"""Unit tests for FastAPI backend endpoints."""

import uuid
import unittest

from fastapi.testclient import TestClient

from api import app


class TestLogicApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_gate_evaluate_and(self):
        response = self.client.post(
            "/api/gates/evaluate",
            json={"gate_type": "and", "inputs": [True, False]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"output": False})

    def test_gate_evaluate_wrong_arity(self):
        response = self.client.post(
            "/api/gates/evaluate",
            json={"gate_type": "not", "inputs": [True, False]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("expects 1 input(s)", response.json()["detail"])

    def test_simulate_simple_and_circuit(self):
        payload = {
            "circuit": {
                "inputs": [
                    {"id": "in_a", "name": "A", "value": True},
                    {"id": "in_b", "name": "B", "value": True},
                ],
                "outputs": [{"id": "out_y", "name": "Y"}],
                "gates": [{"id": "g1", "type": "and", "name": "AND1"}],
                "wires": [
                    {
                        "source_id": "in_a",
                        "source_type": "input",
                        "target_id": "g1",
                        "target_type": "gate",
                        "target_input_index": 0,
                    },
                    {
                        "source_id": "in_b",
                        "source_type": "input",
                        "target_id": "g1",
                        "target_type": "gate",
                        "target_input_index": 1,
                    },
                    {
                        "source_id": "g1",
                        "source_type": "gate",
                        "target_id": "out_y",
                        "target_type": "output",
                        "target_input_index": 0,
                    },
                ],
            }
        }

        response = self.client.post("/api/circuit/simulate", json=payload)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body["output_values"], {"out_y": True})
        self.assertEqual(body["gate_outputs"], {"g1": True})
        self.assertIn("truth_table", body)
        self.assertIn("expressions", body)

    def test_simulate_invalid_gate_input_index(self):
        payload = {
            "circuit": {
                "inputs": [{"id": "in_a", "name": "A", "value": True}],
                "outputs": [{"id": "out_y", "name": "Y"}],
                "gates": [{"id": "g1", "type": "not", "name": "NOT1"}],
                "wires": [
                    {
                        "source_id": "in_a",
                        "source_type": "input",
                        "target_id": "g1",
                        "target_type": "gate",
                        "target_input_index": 1,
                    }
                ],
            }
        }

        response = self.client.post("/api/circuit/simulate", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("out of range", response.json()["detail"])

    def test_save_and_load_circuit(self):
        circuit_name = f"ci_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": circuit_name,
            "circuit": {
                "inputs": [
                    {"id": "in_a", "name": "A", "value": True, "x": 10, "y": 20}
                ],
                "outputs": [{"id": "out_y", "name": "Y", "x": 30, "y": 40}],
                "gates": [
                    {"id": "g_1", "type": "not", "name": "NOT1", "x": 15, "y": 25}
                ],
                "wires": [
                    {
                        "source_id": "in_a",
                        "source_type": "input",
                        "target_id": "g_1",
                        "target_type": "gate",
                        "target_input_index": 0,
                    },
                    {
                        "source_id": "g_1",
                        "source_type": "gate",
                        "target_id": "out_y",
                        "target_type": "output",
                        "target_input_index": 0,
                    },
                ],
            },
        }

        save_response = self.client.post("/api/circuit/save", json=payload)
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()["name"], circuit_name)

        list_response = self.client.get("/api/circuit/list")
        self.assertEqual(list_response.status_code, 200)
        self.assertIn(circuit_name, list_response.json()["circuits"])

        load_response = self.client.get(f"/api/circuit/load/{circuit_name}")
        self.assertEqual(load_response.status_code, 200)
        loaded_circuit = load_response.json()["circuit"]
        self.assertEqual(loaded_circuit["inputs"][0]["name"], "A")
        self.assertEqual(loaded_circuit["gates"][0]["type"], "not")

    def test_load_missing_circuit(self):
        missing_name = f"missing_{uuid.uuid4().hex[:8]}"
        response = self.client.get(f"/api/circuit/load/{missing_name}")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
