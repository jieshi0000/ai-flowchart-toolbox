import pytest
from pydantic import ValidationError

from app.services.diagram_service import (
    compile_diagram_document,
    compile_mermaid,
    validate_diagram_document,
)


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

    @pytest.mark.parametrize(
        "unsafe_text",
        [
            "<script>alert(1)</script>",
            '<img src=x onerror="alert(1)">',
            "javascript:alert(1)",
        ],
    )
    def test_rejects_html_scripts_and_event_attributes(self, unsafe_text):
        with pytest.raises(ValidationError):
            validate_diagram_document(
                _document(nodes=[_node("start", "start", unsafe_text), _node("end", "end")])
            )


class TestMermaidCompiler:
    def test_maps_all_node_types_labels_and_cycles(self):
        document = _document(
            nodes=[
                _node("start", "start", "Start"),
                _node("process", "process", "Process"),
                _node("decision", "decision", "Decision"),
                _node("input", "input_output", "Input"),
                _node("subprocess", "subprocess", "Subprocess"),
                _node("end", "end", "End"),
            ],
            edges=[
                {"id": "e1", "source": "start", "target": "process"},
                {"id": "e2", "source": "process", "target": "decision"},
                {"id": "e3", "source": "decision", "target": "input", "condition": "No"},
                {"id": "e4", "source": "input", "target": "subprocess", "label": "Continue"},
                {"id": "e5", "source": "subprocess", "target": "end"},
                {"id": "e6", "source": "end", "target": "start"},
            ],
        )

        source = compile_mermaid(document)

        assert source == "\n".join(
            [
                "flowchart TB",
                'n0(["Start"])',
                'n1["Process"]',
                'n2{"Decision"}',
                'n3[/"Input"/]',
                'n4[["Subprocess"]]',
                'n5(["End"])',
                "n0 --> n1",
                "n1 --> n2",
                "n2 -->|No| n3",
                "n3 -->|Continue| n4",
                "n4 --> n5",
                "n5 --> n0",
            ]
        )

    def test_uses_requested_lr_direction(self):
        source = compile_mermaid(_document(direction="LR"))

        assert source.startswith("flowchart LR\n")

    def test_escapes_mermaid_control_characters(self):
        label = 'A "quoted" & [bracket] {brace} (round) | pipe / slash \\ hash#; < 3 > 1'
        source = compile_mermaid(
            _document(nodes=[_node("start", "start", label), _node("end", "end")])
        )

        assert (
            'n0(["A &quot;quoted&quot; &amp; &#91;bracket&#93; &#123;brace&#125; '
            '&#40;round&#41; &#124; pipe &#47; slash &#92; hash&#35;&#59; &lt; 3 &gt; 1"])'
        ) in source

    def test_uses_safe_mermaid_aliases_for_contract_node_ids(self):
        source = compile_mermaid(
            _document(
                nodes=[_node("end", "start", "Start"), _node("review-step", "end", "Review")],
                edges=[{"id": "e1", "source": "end", "target": "review-step"}],
            )
        )

        assert source == 'flowchart TB\nn0(["Start"])\nn1(["Review"])\nn0 --> n1'

    def test_replaces_existing_mermaid_source_with_a_derived_value(self):
        document = compile_diagram_document(_document(mermaidSource="flowchart TD\nuntrusted"))

        assert document.mermaid_source == 'flowchart TB\nn0(["Start"])\nn1(["End"])\nn0 --> n1'
