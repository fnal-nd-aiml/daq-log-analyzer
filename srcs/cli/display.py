"""
File: display.py
Purpose: Result display formatting.
Category: Utility
Author: artdaq team
Depends: models, rich
Exports: display_result, display_confident_result, display_uncertain_result, display_insufficient_result, display_contradictory_result, ...
Complexity: Medium | Lines: 197
"""

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree
from srcs.models import InvestigationOutcome, InvestigationResult

OUTCOME_COLORS = {
    InvestigationOutcome.CONFIDENT: "green",
    InvestigationOutcome.PROBABLE: "yellow",
    InvestigationOutcome.UNCERTAIN: "orange1",
    InvestigationOutcome.INSUFFICIENT: "red",
    InvestigationOutcome.CONTRADICTORY: "red",
}
OUTCOME_DESCRIPTIONS = {
    InvestigationOutcome.CONFIDENT: "High confidence in root cause",
    InvestigationOutcome.PROBABLE: "Likely root cause identified",
    InvestigationOutcome.UNCERTAIN: "Multiple hypotheses remain viable",
    InvestigationOutcome.INSUFFICIENT: "Insufficient evidence for conclusion",
    InvestigationOutcome.CONTRADICTORY: "Evidence contradicts itself",
}


def display_result(console: Console, result: InvestigationResult, verbose: bool = False) -> None:
    color = OUTCOME_COLORS.get(result.outcome, "white")
    description = OUTCOME_DESCRIPTIONS.get(result.outcome, "")
    console.print()
    console.print(
        Panel(f"[bold {color}]{result.outcome.value}[/]\n[dim]{description}[/dim]", title="Investigation Outcome")
    )
    if result.outcome in [InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE]:
        display_confident_result(console, result, verbose)
    elif result.outcome == InvestigationOutcome.UNCERTAIN:
        display_uncertain_result(console, result, verbose)
    elif result.outcome == InvestigationOutcome.INSUFFICIENT:
        display_insufficient_result(console, result)
    elif result.outcome == InvestigationOutcome.CONTRADICTORY:
        display_contradictory_result(console, result)
    console.print()
    console.print(f"[dim]Investigation completed in {result.duration_seconds:.1f}s[/dim]")
    console.print(f"[dim]Investigation ID: {result.investigation_id}[/dim]")


def display_confident_result(console: Console, result: InvestigationResult, verbose: bool) -> None:
    if result.root_cause:
        confidence = result.root_cause.confidence
        rc = result.root_cause
        console.print()
        console.print(
            Panel(
                f"[bold]Root Cause:[/bold]\n{rc.root_cause}\n\n[bold]Confidence:[/bold] {confidence.calibrated:.0%} (raw: {confidence.raw:.0%})",
                title="Conclusion",
            )
        )
        if confidence.calibration_notes:
            console.print("[dim]Calibration: " + ", ".join(confidence.calibration_notes) + "[/dim]")
        if rc.code_location:
            console.print(f"\n[bold]Error Location:[/bold] [cyan]{rc.code_location}[/cyan]")
        if rc.code_snippet:
            console.print("\n[bold]Code Context:[/bold]")
            syntax = Syntax(rc.code_snippet, "cpp", theme="monokai", line_numbers=False, word_wrap=True)
            console.print(syntax)
        if rc.sub_causes:
            console.print("\n[bold]Ranked Causes:[/bold]")
            table = Table(show_header=True, header_style="bold", box=None)
            table.add_column("Cause", style="white", no_wrap=False)
            table.add_column("Prob", justify="right", style="cyan", width=6)
            table.add_column("Diagnostic", style="dim", no_wrap=False)
            for sc in rc.sub_causes[:6]:
                prob_color = "green" if sc.probability >= 0.3 else "yellow" if sc.probability >= 0.1 else "dim"
                table.add_row(
                    sc.description[:60] + ("..." if len(sc.description) > 60 else ""),
                    f"[{prob_color}]{sc.probability:.0%}[/{prob_color}]",
                    sc.evidence_summary[:50] if sc.evidence_summary else "",
                )
            console.print(table)
        if rc.data_flow:
            console.print("\n[bold]Data Flow:[/bold]")
            console.print(f"[dim]{rc.data_flow}[/dim]")
        if rc.key_files:
            console.print("\n[bold]Key Files:[/bold]")
            table = Table(show_header=True, header_style="bold", box=None)
            table.add_column("File", style="cyan", no_wrap=True)
            table.add_column("Purpose", style="white")
            table.add_column("Lines", style="dim", width=15)
            for kf in rc.key_files[:5]:
                table.add_row(kf.file_path, kf.purpose, kf.line_range or "")
            console.print(table)
        if rc.debugging_steps:
            console.print("\n[bold]Debugging Steps:[/bold]")
            for i, step in enumerate(rc.debugging_steps[:7], 1):
                console.print(f"  [cyan]{i}.[/cyan] {step}")
        if rc.caveats and verbose:
            console.print("\n[bold]Caveats:[/bold]")
            for caveat in rc.caveats:
                console.print(f"  [dim]• {caveat}[/dim]")
    if verbose and result.causal_chain and result.causal_chain.steps:
        console.print("\n[bold]Causal Chain:[/bold]")
        tree = Tree("[bold]Root Cause[/bold]")
        for step in result.causal_chain.steps:
            evidence_note = f"[{step.evidence_strength}]"
            if step.is_assumption:
                evidence_note = "[dim]ASSUMPTION[/dim]"
            node = tree.add(f"{step.claim} {evidence_note}")
            if step.mechanism:
                node.add(f"[dim]→ {step.mechanism}[/dim]")
        console.print(tree)
    if result.recommendations:
        console.print("\n[bold]General Recommendations:[/bold]")
        for rec in result.recommendations:
            console.print(f"  • {rec}")
    if result.alternatives and verbose:
        console.print("\n[bold]Alternative Hypotheses:[/bold]")
        for alt in result.alternatives:
            score_color = "green" if alt.score > 0.5 else "yellow" if alt.score > 0.3 else "dim"
            desc = alt.description[:80] + ("..." if len(alt.description) > 80 else "")
            console.print(f"  • {desc} [{score_color}]{alt.score:.0%}[/{score_color}]")


def display_uncertain_result(console: Console, result: InvestigationResult, verbose: bool) -> None:
    console.print()
    console.print(
        Panel(
            "[yellow]Multiple hypotheses remain viable. More evidence is needed to discriminate between them.[/yellow]",
            title="Uncertain Outcome",
        )
    )
    if result.viable_hypotheses:
        table = Table(title="Viable Hypotheses")
        table.add_column("Hypothesis", style="white")
        table.add_column("Score", justify="right", style="cyan")
        for h in result.viable_hypotheses:
            score_color = "green" if h.score > 0.5 else "yellow" if h.score > 0.3 else "white"
            table.add_row(
                h.description[:70] + "..." if len(h.description) > 70 else h.description,
                f"[{score_color}]{h.score:.0%}[/{score_color}]",
            )
        console.print(table)
    if result.discrimination_needed:
        console.print("\n[bold]To Discriminate:[/bold]")
        for d in result.discrimination_needed:
            console.print(f"  • {d}")
    if result.recommendations:
        console.print("\n[bold]Recommended Next Steps:[/bold]")
        for rec in result.recommendations:
            console.print(f"  • {rec}")


def display_insufficient_result(console: Console, result: InvestigationResult) -> None:
    console.print()
    console.print(
        Panel(
            f"[red]{result.insufficient_reason or 'Insufficient evidence to reach conclusion'}[/red]",
            title="Insufficient Evidence",
        )
    )
    if result.missing_evidence:
        console.print("\n[bold]Missing Evidence:[/bold]")
        for m in result.missing_evidence:
            console.print(f"  • {m}")
    if result.viable_hypotheses:
        console.print(
            """
[bold]Best Guesses (unconfirmed):[/bold]"""
        )
        for h in result.viable_hypotheses[:3]:
            console.print(f"  • {h.description[:70]}... ({h.score:.0%})")


def display_contradictory_result(console: Console, result: InvestigationResult) -> None:
    console.print()
    console.print(
        Panel(
            "[red]Evidence contradicts itself - multiple incompatible explanations found.[/red]",
            title="Contradictory Evidence",
        )
    )
    if result.insufficient_reason:
        console.print(f"\n[dim]{result.insufficient_reason}[/dim]")
    if result.viable_hypotheses:
        console.print("\n[bold]Conflicting Hypotheses:[/bold]")
        for h in result.viable_hypotheses:
            console.print(f"  • {h.description[:70]}... ({h.score:.0%})")
    if result.missing_evidence:
        console.print(
            """
[bold]Evidence Needed to Resolve:[/bold]"""
        )
        for m in result.missing_evidence:
            console.print(f"  • {m}")


def display_evidence_summary(console: Console, summary: str) -> None:
    if summary and summary != "No evidence collected":
        console.print("\n[bold]Evidence Summary:[/bold]")
        for line in summary.split("\n"):
            console.print(f"  {line}")
