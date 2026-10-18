"""Scenarios served by one deployment. Each has its own immutable bundle and sources."""

from dataclasses import dataclass

SCENARIO_HEADER = "x-regimpact-scenario"


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    scenario_id: str
    seed: str
    catalog: str
    evidence: str | None
    source_manifest: str
    demo_catalog: str
    label: str


MAS_2023 = ScenarioSpec(
    key="mas-2023",
    scenario_id="SCENARIO-MAS-2023",
    seed="seed/baseline.json",
    catalog="synthetic/catalog.json",
    evidence="public/source-evidence.json",
    source_manifest="source-manifest.json",
    demo_catalog="seed/demo_catalog.json",
    label="Marketing rules · 2023 proposal",
)
TRM_2021 = ScenarioSpec(
    key="trm-2021",
    scenario_id="SCENARIO-TRM-2021",
    seed="seed/trm_baseline.json",
    catalog="synthetic/trm_catalog.json",
    evidence=None,
    source_manifest="trm-source-manifest.json",
    demo_catalog="seed/trm_demo_catalog.json",
    label="Technology risk · 2021 final",
)
SCENARIOS = (MAS_2023, TRM_2021)


def enabled_scenarios(keys: str) -> tuple[ScenarioSpec, ...]:
    wanted = [key.strip() for key in keys.split(",") if key.strip()]
    known = {spec.key: spec for spec in SCENARIOS}
    unknown = [key for key in wanted if key not in known]
    if unknown or not wanted:
        raise ValueError(f"Unknown or empty scenario selection: {unknown or keys!r}")
    return tuple(known[key] for key in wanted)
