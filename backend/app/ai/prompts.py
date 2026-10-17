from pathlib import Path

PROMPT_DIRECTORY = Path(__file__).resolve().parents[1] / "prompts"
VERSIONS = frozenset(
    {
        "interpret-v1",
        "interpret-v2",
        "risk-map-v1",
        "policy-map-v1",
        "pcs-extract-v1",
        "pcs-extract-v2",
        "change-effect-v1",
        "impact-explain-v1",
        "ask-regimpact-v1",
    }
)


def load_prompt(version: str) -> str:
    if version not in VERSIONS:
        raise ValueError("Unregistered prompt version")
    return (PROMPT_DIRECTORY / f"{version}.prompt").read_text(encoding="utf-8")
