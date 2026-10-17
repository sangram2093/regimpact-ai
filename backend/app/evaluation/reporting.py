"""Reports keep raw denominators and software-only results visibly distinct."""

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    provenance = report["provenance"]
    lines = [
        "# RegImpact AI evaluation",
        "",
        f"Status: **{provenance['status']}**",
        "",
        f"Dataset: `{report['dataset_id']}` · Split: `{report['split']}`",
        f"Run: `{report['run_id']}` · Cases: {report['case_count']}",
        f"Execution: `{report['execution_mode']}` · Model: `{report['model'] or 'none'}`",
        "",
    ]
    if provenance["status"] == "SOFTWARE_TEST_ONLY":
        lines.extend(
            [
                "These are synthetic software fixtures. "
                "These scores are **not blind model accuracy**",
                "and must not be used as competition model-quality or business-impact evidence.",
                "",
            ]
        )
    lines.extend(
        [
            "| Metric | Numerator | Denominator | Rate |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name, metric in report["metrics"].items():
        rate = "N/A" if metric["rate"] is None else f"{metric['rate']:.2%}"
        lines.append(f"| {name} | {metric['numerator']} | {metric['denominator']} | {rate} |")
    lines.extend(
        [
            "",
            "For false carry-forward, the numerator is the error count; lower is better.",
            "",
            "## Provenance",
            "",
        ]
    )
    lines.extend(f"- {key}: `{value}`" for key, value in provenance.items())
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {limit}" for limit in report["limitations"])
    if report["schema_errors"]:
        lines.extend(["", "## Invalid normalized outputs", ""])
        lines.extend(
            f"- `{error['case_id']}`: schema validation failed; expectations still count."
            for error in report["schema_errors"]
        )
    return "\n".join(lines) + "\n"
