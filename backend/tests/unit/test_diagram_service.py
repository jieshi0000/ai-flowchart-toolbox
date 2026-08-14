import pytest
from pydantic import ValidationError

from app.services.diagram_service import validate_diagram_document


def _node(node_id: str, node_type: str = "process", label: str | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "label": label or node_id,
        "position": {"x": 0, "y": 0},
    }


def _document(**overrides) -> dict:
    payload = {
        "title": "Example flow",
        "direction": "TB",
        "nodes": [_node("start", "start", "Start"), _node("end", "end", "End")],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }
    payload.update(overrides)
    return payload


class TestDiagramDocumentValidator:
    def test_accepts_the_document_boundary_limits(self):
        nodes = [_node(f"n{index}") for index in range(50)]
        edges = [
            {"id": f"e{index}", "source": "n0", "target": "n1"}
            for index in range(100)
        ]

        document = validate_diagram_document(_document(nodes=nodes, edges=edges))

        assert len(document.nodes) == 50
        assert len(document.edges) == 100

    @pytest.mark.parametrize(
        "payload",
        [
            _document(nodes=[_node(f"n{index}") for index in range(51)]),
            _document(
                nodes=[_node("n0"), _node("n1")],
                edges=[
                    {"id": f"e{index}", "source": "n0", "target": "n1"}
                    for index in range(101)
                ],
            ),
            _document(edges=[{"id": "e1", "source": "missing", "target": "end"}]),
        ],
    )
    def test_rejects_invalid_document_boundaries(self, payload):
        with pytest.raises(ValidationError):
            validate_diagram_document(payload)
