import json
from pathlib import Path

from app.config.scenarios import MAS_2023, ScenarioSpec
from app.domain.graph import ApprovedControlPath, approved_control_paths
from app.domain.models import BaselineEdge, SeedBundle


class LocalJsonRepository:
    """Validate once; expose deeply immutable Pydantic models and tuples."""

    def __init__(self, data_dir: Path, spec: ScenarioSpec = MAS_2023) -> None:
        baseline = json.loads((data_dir / spec.seed).read_text(encoding="utf-8"))
        catalog = json.loads((data_dir / spec.catalog).read_text(encoding="utf-8"))
        baseline["catalog"] = catalog["nodes"]
        baseline["edges"].extend(catalog["edges"])
        evidence_path = data_dir / spec.evidence if spec.evidence else None
        if evidence_path and evidence_path.exists():
            verified = json.loads(evidence_path.read_text(encoding="utf-8"))
            by_id = {segment["segment_id"]: segment for segment in verified["segments"]}
            for evidence in baseline["evidence"]:
                if evidence["id"] in by_id:
                    segment = by_id[evidence["id"]]
                    for key in (
                        "source_id",
                        "source_url",
                        "paragraph_ref",
                        "page",
                        "text",
                        "text_kind",
                        "verification_status",
                        "data_origin",
                    ):
                        evidence[key] = segment[key]
        self._bundle = SeedBundle.model_validate(baseline)

    def snapshot(self) -> SeedBundle:
        return self._bundle

    def approved_outgoing(self, node_id: str) -> tuple[BaselineEdge, ...]:
        return tuple(
            edge
            for edge in self._bundle.edges
            if edge.source_id == node_id and edge.status == "APPROVED"
        )

    def approved_control_paths(self, mandate_id: str) -> tuple[ApprovedControlPath, ...]:
        return approved_control_paths(self._bundle, mandate_id)
