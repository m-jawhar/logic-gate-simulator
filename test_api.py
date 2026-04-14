"""Unit tests for FastAPI backend endpoints."""

import unittest
import uuid

from fastapi.testclient import TestClient

from api import app


class TestLogicApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.username = f"user_{uuid.uuid4().hex[:8]}"
        self.password = "password123"

        register_response = self.client.post(
            "/api/auth/register",
            json={"username": self.username, "password": self.password},
        )
        self.assertEqual(register_response.status_code, 200)
        token = register_response.json()["access_token"]
        self.auth_headers = {"Authorization": f"Bearer {token}"}

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

    def test_simulate_partially_connected_circuit_returns_nullable_truth_rows(self):
        payload = {
            "circuit": {
                "inputs": [
                    {"id": "in_a", "name": "A", "value": False},
                    {"id": "in_b", "name": "B", "value": False},
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
                ],
            }
        }

        response = self.client.post("/api/circuit/simulate", json=payload)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertIsNone(body["output_values"]["out_y"])
        rows = body["truth_table"]["rows"]
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertIsNone(row[2])

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

        save_response = self.client.post(
            "/api/circuit/save",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()["name"], circuit_name)

        list_response = self.client.get("/api/circuit/list", headers=self.auth_headers)
        self.assertEqual(list_response.status_code, 200)
        self.assertIn(circuit_name, list_response.json()["circuits"])

        load_response = self.client.get(
            f"/api/circuit/load/{circuit_name}", headers=self.auth_headers
        )
        self.assertEqual(load_response.status_code, 200)
        loaded_circuit = load_response.json()["circuit"]
        self.assertEqual(loaded_circuit["inputs"][0]["name"], "A")
        self.assertEqual(loaded_circuit["gates"][0]["type"], "not")

    def test_load_missing_circuit(self):
        missing_name = f"missing_{uuid.uuid4().hex[:8]}"
        response = self.client.get(
            f"/api/circuit/load/{missing_name}", headers=self.auth_headers
        )
        self.assertEqual(response.status_code, 404)

    def test_auth_login(self):
        login_response = self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": self.password},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("access_token", login_response.json())

    def test_persistence_requires_auth(self):
        response = self.client.get("/api/circuit/list")
        self.assertEqual(response.status_code, 401)

    def test_public_shared_circuit_read_only_link(self):
        circuit_name = f"ci_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": circuit_name,
            "circuit": {
                "inputs": [{"id": "in_a", "name": "A", "value": True}],
                "outputs": [{"id": "out_y", "name": "Y"}],
                "gates": [],
                "wires": [
                    {
                        "source_id": "in_a",
                        "source_type": "input",
                        "target_id": "out_y",
                        "target_type": "output",
                        "target_input_index": 0,
                    }
                ],
            },
        }

        save_response = self.client.post(
            "/api/circuit/save",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(save_response.status_code, 200)

        share_response = self.client.post(
            f"/api/circuit/share/{circuit_name}",
            headers=self.auth_headers,
        )
        self.assertEqual(share_response.status_code, 200)
        share_id = share_response.json()["share_id"]

        public_load_response = self.client.get(f"/api/public/circuit/{share_id}")
        self.assertEqual(public_load_response.status_code, 200)
        self.assertEqual(
            public_load_response.json()["circuit"]["inputs"][0]["name"], "A"
        )

    def test_timing_diagram_endpoint(self):
        payload = {
            "circuit": {
                "inputs": [
                    {"id": "in_a", "name": "A", "value": False},
                    {"id": "in_b", "name": "B", "value": False},
                ],
                "outputs": [{"id": "out_y", "name": "Y"}],
                "gates": [{"id": "g1", "type": "or", "name": "OR1"}],
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

        response = self.client.post("/api/circuit/timing", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("steps", body)
        self.assertIn("signals", body)
        self.assertGreaterEqual(len(body["steps"]), 1)

    def test_create_and_use_custom_gate(self):
        create_payload = {
            "name": "my_and",
            "output_name": "Y",
            "circuit": {
                "inputs": [
                    {"id": "in_a", "name": "A", "value": False},
                    {"id": "in_b", "name": "B", "value": False},
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
            },
        }

        create_response = self.client.post(
            "/api/custom-gates/create",
            json=create_payload,
            headers=self.auth_headers,
        )
        self.assertEqual(create_response.status_code, 200)

        list_response = self.client.get("/api/custom-gates", headers=self.auth_headers)
        self.assertEqual(list_response.status_code, 200)
        self.assertTrue(
            any(g["name"] == "my_and" for g in list_response.json()["gates"])
        )

        simulate_payload = {
            "circuit": {
                "inputs": [
                    {"id": "in_a", "name": "A", "value": True},
                    {"id": "in_b", "name": "B", "value": True},
                ],
                "outputs": [{"id": "out_y", "name": "Y"}],
                "gates": [
                    {"id": "g_custom", "type": "custom:my_and", "name": "MYAND1"}
                ],
                "wires": [
                    {
                        "source_id": "in_a",
                        "source_type": "input",
                        "target_id": "g_custom",
                        "target_type": "gate",
                        "target_input_index": 0,
                    },
                    {
                        "source_id": "in_b",
                        "source_type": "input",
                        "target_id": "g_custom",
                        "target_type": "gate",
                        "target_input_index": 1,
                    },
                    {
                        "source_id": "g_custom",
                        "source_type": "gate",
                        "target_id": "out_y",
                        "target_type": "output",
                        "target_input_index": 0,
                    },
                ],
            }
        }

        simulate_response = self.client.post(
            "/api/circuit/simulate",
            json=simulate_payload,
            headers=self.auth_headers,
        )
        self.assertEqual(simulate_response.status_code, 200)
        self.assertEqual(simulate_response.json()["output_values"]["out_y"], True)

    def test_share_and_import_custom_gate_between_users(self):
        create_payload = {
            "name": "shared_and",
            "output_name": "Y",
            "circuit": {
                "inputs": [
                    {"id": "in_a", "name": "A", "value": False},
                    {"id": "in_b", "name": "B", "value": False},
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
            },
        }

        create_response = self.client.post(
            "/api/custom-gates/create",
            json=create_payload,
            headers=self.auth_headers,
        )
        self.assertEqual(create_response.status_code, 200)

        share_response = self.client.post(
            "/api/custom-gates/share/shared_and",
            headers=self.auth_headers,
        )
        self.assertEqual(share_response.status_code, 200)
        share_id = share_response.json()["share_id"]

        public_response = self.client.get(f"/api/public/custom-gates/{share_id}")
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.json()["name"], "shared_and")

        other_username = f"user_{uuid.uuid4().hex[:8]}"
        other_password = "password123"
        register_response = self.client.post(
            "/api/auth/register",
            json={"username": other_username, "password": other_password},
        )
        self.assertEqual(register_response.status_code, 200)
        other_token = register_response.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        import_response = self.client.post(
            f"/api/custom-gates/import/{share_id}",
            json={},
            headers=other_headers,
        )
        self.assertEqual(import_response.status_code, 200)

        simulate_payload = {
            "circuit": {
                "inputs": [
                    {"id": "in_a", "name": "A", "value": True},
                    {"id": "in_b", "name": "B", "value": True},
                ],
                "outputs": [{"id": "out_y", "name": "Y"}],
                "gates": [
                    {
                        "id": "g_custom",
                        "type": "custom:shared_and",
                        "name": "SHAREDAND1",
                    }
                ],
                "wires": [
                    {
                        "source_id": "in_a",
                        "source_type": "input",
                        "target_id": "g_custom",
                        "target_type": "gate",
                        "target_input_index": 0,
                    },
                    {
                        "source_id": "in_b",
                        "source_type": "input",
                        "target_id": "g_custom",
                        "target_type": "gate",
                        "target_input_index": 1,
                    },
                    {
                        "source_id": "g_custom",
                        "source_type": "gate",
                        "target_id": "out_y",
                        "target_type": "output",
                        "target_input_index": 0,
                    },
                ],
            }
        }

        simulate_response = self.client.post(
            "/api/circuit/simulate",
            json=simulate_payload,
            headers=other_headers,
        )
        self.assertEqual(simulate_response.status_code, 200)
        self.assertEqual(simulate_response.json()["output_values"]["out_y"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
