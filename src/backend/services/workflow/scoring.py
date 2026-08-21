"""
Scores an autonomous run against the synthetic dataset's ground truth.

Grades what the agent actually did, taken from recorded act steps, separately
from what it claimed in prose, because a model can narrate work it never
performed. Pure logic: callers supply the ground truth and the trail.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from services.workflow.model_text import strip_reasoning

# Ground truth keys, read from the generator's ground_truth.json.
KEY_FINDINGS = "expected_findings"
KEY_EQUIPMENT = "machine_id"
KEY_DIRECTION = "expected_direction"
KEY_PROFILE = "profile_kind"
KEY_HEADLINE = "headline_equipment"

# A finding whose expected direction is this is a negative control: the machine
# is healthy and flagging it is a false positive, not a near miss.
DIRECTION_NO_FINDING = "no_finding"
KEY_METRIC = "metric"

# Metrics this system actually analyses. The generator still plants defects for
# signal families that were trimmed from the project scope -- mean time between
# failures, mean time to repair, and a stability decline encoded in hard-stop
# rate rather than duration variance. None of those are computed anywhere in the
# analysis layer, so scoring against them measures the dataset's ambition rather
# than the agent's behaviour. Machines carrying only an out-of-scope defect are
# excluded from the score entirely: not counted as missed, and not counted as a
# false positive if named.
IN_SCOPE_METRICS = frozenset({"deviation_pct"})


def _is_in_scope(finding: Dict[str, Any]) -> bool:
    """Report whether a planted defect is one this system can detect.

    Fails open: a contract that does not name a metric is treated as in scope,
    since absence of the field is not evidence that the defect is undetectable.
    Only an explicitly named, unimplemented metric is excluded.

    Args:
        finding: One entry from the contract's expected_findings.

    Returns:
        True when the defect should be scored.
    """
    metric = finding.get(KEY_METRIC)
    if metric is None:
        return True
    return metric in IN_SCOPE_METRICS

# Trail keys.
KEY_PHASE = "phase"
KEY_PAYLOAD = "payload"
PHASE_ACT = "act"

# Equipment codes look like MX-7103. Matching on this shape rather than
# scanning for known codes means a hallucinated machine is still detected.
EQUIPMENT_PATTERN = re.compile(r"\b[A-Z]{2,4}-\d{3,5}\b")

# A machine-readable verdict the agent is asked to end its summary with, e.g.
# "FLAGGED: MX-7103" or "FLAGGED: NONE". Naming a machine in prose cannot
# distinguish flagging it from clearing it, and a summary that lists healthy
# machines by name scores every one of them as a false positive. This line is
# the unambiguous signal; the prose heuristic remains the fallback.
VERDICT_PATTERN = re.compile(r"^\s*FLAGGED\s*:\s*(.+?)\s*$", re.MULTILINE)
VERDICT_NONE = "NONE"


# Payload keys that carry equipment codes, singular and plural.
EQUIPMENT_ARG_KEYS = ("machine_id", "machine_ids")

ZERO_DIVISION_RESULT = 0.0


@dataclass
class ScoreReport:
    """The outcome of scoring one run against ground truth."""

    true_positives: List[str] = field(default_factory=list)
    false_positives: List[str] = field(default_factory=list)
    false_negatives: List[str] = field(default_factory=list)
    investigated: List[str] = field(default_factory=list)
    claimed_only: List[str] = field(default_factory=list)
    headline_found: bool = False

    @property
    def precision(self) -> float:
        """Share of flagged machines that were genuinely defective."""
        flagged = len(self.true_positives) + len(self.false_positives)
        return len(self.true_positives) / flagged if flagged else ZERO_DIVISION_RESULT

    @property
    def recall(self) -> float:
        """Share of planted defects the agent flagged."""
        total = len(self.true_positives) + len(self.false_negatives)
        return len(self.true_positives) / total if total else ZERO_DIVISION_RESULT

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall."""
        if not self.precision or not self.recall:
            return ZERO_DIVISION_RESULT
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the report for printing or storage."""
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "investigated": self.investigated,
            "claimed_only": self.claimed_only,
            "headline_found": self.headline_found,
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "f1": round(self.f1, 3),
        }


def expected_defects(ground_truth: Dict[str, Any]) -> Set[str]:
    """
    Return equipment codes carrying a planted, in-scope defect.

    Defects planted for signal families outside this system's analysis scope
    are skipped; see IN_SCOPE_METRICS.

    Args:
        ground_truth: Parsed ground_truth.json.

    Returns:
        Codes the agent is expected to flag.
    """
    return {
        finding[KEY_EQUIPMENT]
        for finding in ground_truth.get(KEY_FINDINGS, [])
        if finding.get(KEY_DIRECTION) != DIRECTION_NO_FINDING
        and _is_in_scope(finding)
    }


def out_of_scope_defects(ground_truth: Dict[str, Any]) -> Set[str]:
    """Return equipment whose only planted defect is outside analysis scope.

    Reported so a run is not silently graded against signals the system was
    never built to detect.

    Args:
        ground_truth: Parsed ground_truth.json.

    Returns:
        Codes excluded from both the defect and control sets.
    """
    return {
        finding[KEY_EQUIPMENT]
        for finding in ground_truth.get(KEY_FINDINGS, [])
        if finding.get(KEY_DIRECTION) != DIRECTION_NO_FINDING
        and not _is_in_scope(finding)
    } - expected_defects(ground_truth)


def negative_controls(ground_truth: Dict[str, Any]) -> Set[str]:
    """
    Return equipment codes that are healthy and must not be flagged.

    Args:
        ground_truth: Parsed ground_truth.json.

    Returns:
        Codes for which a flag counts as a false positive.
    """
    return {
        finding[KEY_EQUIPMENT]
        for finding in ground_truth.get(KEY_FINDINGS, [])
        if finding.get(KEY_DIRECTION) == DIRECTION_NO_FINDING
    }


def extract_mentioned_equipment(text: str) -> Set[str]:
    """
    Find equipment codes the agent named in its conclusion.

    This is a heuristic: naming a machine is treated as flagging it. It is
    deliberately applied to the conclusion only, never the scratchpad, but a
    conclusion that names a machine merely to clear it will still be counted.
    Use the investigated set for a claim that does not depend on prose.

    Args:
        text: The agent's final output.

    Returns:
        Every code-shaped token in the conclusion.
    """
    return set(EQUIPMENT_PATTERN.findall(strip_reasoning(text)))


def extract_verdict_equipment(text: str) -> Optional[Set[str]]:
    """Read the agent's explicit FLAGGED verdict line, if it wrote one.

    Args:
        text: The agent's final output.

    Returns:
        The flagged codes, an empty set when the verdict is NONE, or None when
        no verdict line is present.
    """
    match = VERDICT_PATTERN.search(strip_reasoning(text))
    if match is None:
        return None
    value = match.group(1).strip()
    if value.upper().startswith(VERDICT_NONE):
        return set()
    return set(EQUIPMENT_PATTERN.findall(value))


def extract_flagged_equipment(text: str) -> Set[str]:
    """Determine which machines the agent flagged.

    Prefers the explicit verdict line, falling back to naming-as-flagging when
    the agent did not write one.

    Args:
        text: The agent's final output.

    Returns:
        The set of flagged equipment codes.
    """
    verdict = extract_verdict_equipment(text)
    if verdict is not None:
        return verdict
    return extract_mentioned_equipment(text)


def extract_investigated_equipment(steps: List[Dict[str, Any]]) -> Set[str]:
    """
    Find equipment the agent actually acted on, from recorded act steps.

    This is the honest signal. A run that names a machine only in prose did no
    work on it, however confidently it says otherwise.

    Args:
        steps: Decision trail steps, as returned by load_trail.

    Returns:
        Codes appearing in the arguments of act-phase tool calls.
    """
    found: Set[str] = set()
    for step in steps:
        if step.get(KEY_PHASE) != PHASE_ACT:
            continue
        payload = step.get(KEY_PAYLOAD) or {}
        for key in EQUIPMENT_ARG_KEYS:
            value = payload.get(key)
            if isinstance(value, str):
                found.add(value)
            elif isinstance(value, list):
                found.update(item for item in value if isinstance(item, str))
    return found


def score_run(
    ground_truth: Dict[str, Any],
    summary_text: str,
    steps: List[Dict[str, Any]],
) -> ScoreReport:
    """
    Score one autonomous run.

    A machine counts as flagged when the agent named it in its summary. What it
    investigated is tracked separately, so a gap between the two is visible
    rather than being quietly credited as work done.

    Args:
        ground_truth: Parsed ground_truth.json.
        summary_text: The agent's closing summary.
        steps: Decision trail steps for the run.

    Returns:
        The scored report.
    """
    defects = expected_defects(ground_truth)
    controls = negative_controls(ground_truth)

    flagged = extract_flagged_equipment(summary_text)
    investigated = extract_investigated_equipment(steps)

    return ScoreReport(
        true_positives=sorted(flagged & defects),
        false_positives=sorted(flagged & controls),
        false_negatives=sorted(defects - flagged),
        investigated=sorted(investigated),
        claimed_only=sorted(flagged - investigated),
        headline_found=ground_truth.get(KEY_HEADLINE) in flagged,
    )
