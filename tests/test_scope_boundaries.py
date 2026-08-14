import ast
import re
from pathlib import Path

from hsconfig.external_skill_bundle import load_embedded_skill_bundle


FORBIDDEN_SRC_CONCEPTS = (
    (
        "replay parsing",
        re.compile(r"\breplay[\s_-]*(?:parsing|parser)\b|\bparse_replay\b", re.I),
    ),
    (
        "HDT parsing",
        re.compile(
            r"\bhdt[\s_-]*(?:parsing|parser|replay)\b|\bhs[\s_-]*replay\b|\bparse_hdt_replay\b|\bhdt_replay\b",
            re.I,
        ),
    ),
    (
        "Power.log parsing",
        re.compile(
            r"\bpower(?:\.|[\s_-]*)log(?=\b|parsing\b|parser\b|[\s_-])(?:[\s_-]*(?:parsing|parser))?|\bparse_power_log\b",
            re.I,
        ),
    ),
    (
        "winrate validation",
        re.compile(
            r"\bwinrate(?=\b|validation\b|validator\b|analysis\b|analyzer\b|[\s_-])(?:[\s_-]*(?:validation|validator|analysis|analyzer))?",
            re.I,
        ),
    ),
    (
        "post-run tuning",
        re.compile(r"\bpost(?:game|[\s_-]*run)[\s_-]*(?:tuning|tuner)\b", re.I),
    ),
    (
        "candidate promotion",
        re.compile(r"\bcandidate[\s_-]*promotion\b|\banalyze[\s_-]*step2\b", re.I),
    ),
)

REQUIRED_DOC_PHRASES = (
    "hdt_deck_id is identity-only metadata",
    "not replay evidence",
)
FORBIDDEN_AUTONOMOUS_MULLIGAN_SOURCE_TYPE = (
    "policy_backed_autonomous_mulligan"
)
FORBIDDEN_LEGACY_MULLIGAN_HELPERS = {
    "_filter_mulligan_plan",
    "_has_concrete_mulligan_hold",
    "_is_unreferenced_wildcard_discard",
    "mulligan_rule_key",
    "validated_mulligan_source_gap_vetoes",
}


def _forbidden_source_concepts(text):
    return [
        concept
        for concept, pattern in FORBIDDEN_SRC_CONCEPTS
        if pattern.search(text)
    ]


def test_scope_guard_terms_cover_likely_source_spellings():
    sample_spellings = {
        "replay parsing": [
            "replay parsing",
            "replay parser",
            "ReplayParser",
            "parse_replay",
        ],
        "HDT parsing": [
            "HDT parsing",
            "HDT parser",
            "hsreplay",
            "hs_replay",
            "hs-replay",
            "parse_hdt_replay",
            "hdt_replay",
        ],
        "Power.log parsing": [
            "Power.log",
            "Power.log parsing",
            "PowerLogParser",
            "parse_power_log",
        ],
        "winrate validation": [
            "winrate",
            "winrate validation",
            "winrate analyzer",
        ],
        "post-run tuning": [
            "postgame tuning",
            "post-run tuner",
            "post-run tuning",
        ],
        "candidate promotion": [
            "candidate promotion",
            "analyze-step2",
        ],
    }

    misses = []
    for concept, spellings in sample_spellings.items():
        for spelling in spellings:
            if concept not in _forbidden_source_concepts(spelling):
                misses.append(f"{concept}:{spelling}")

    assert misses == []


def test_scope_guard_patterns_allow_identity_safe_terms():
    allowed_samples = [
        "hdt_deck_id = deck_identity['hdt_deck_id']",
        "parse_deck_identity(raw_deck)",
        "strong_promotion_report.json",
        "candidate_archetypes.json",
        "hdt_metadata = {'source': 'deck identity'}",
    ]

    offenders = {
        sample: _forbidden_source_concepts(sample)
        for sample in allowed_samples
        if _forbidden_source_concepts(sample)
    }

    assert offenders == {}


def test_hsconfig_src_does_not_absorb_post_run_scope():
    offenders = []
    for path in sorted(Path("src/hsconfig").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for concept in _forbidden_source_concepts(text):
            offenders.append(f"{path}:{concept}")

    assert offenders == []


def test_active_code_has_no_obsolete_autonomous_mulligan_source_type():
    guard_path = Path(__file__).resolve()
    offenders = []
    for root in (Path("src"), Path("tests"), Path("scripts")):
        for path in sorted(root.rglob("*")):
            if (
                not path.is_file()
                or "__pycache__" in path.parts
                or any(part.endswith(".egg-info") for part in path.parts)
                or path.resolve() == guard_path
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if FORBIDDEN_AUTONOMOUS_MULLIGAN_SOURCE_TYPE in text:
                offenders.append(str(path))

    assert offenders == []


def test_hsconfig_src_has_no_obsolete_mulligan_compatibility_helpers():
    offenders = []
    for path in sorted(Path("src/hsconfig").rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in FORBIDDEN_LEGACY_MULLIGAN_HELPERS
            ):
                offenders.append(f"{path}:{node.lineno}:{node.name}")

    assert offenders == []


def test_operator_docs_explain_hdt_as_identity_only():
    missing = []
    documents = {
        "docs/operator/README.md": Path("docs/operator/README.md").read_text(
            encoding="utf-8"
        ),
        "embedded:references/workflow.md": load_embedded_skill_bundle()[
            "references/workflow.md"
        ].decode("utf-8"),
    }
    for path, text in documents.items():
        for phrase in REQUIRED_DOC_PHRASES:
            if phrase not in text:
                missing.append(f"{path}:{phrase}")

    assert missing == []


def test_active_docs_keep_hstuner_scope_as_negative_boundary():
    embedded = load_embedded_skill_bundle()
    combined = "\n".join(
        (
            Path("README.md").read_text(encoding="utf-8"),
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            embedded["SKILL.md"].decode("utf-8"),
            embedded["references/workflow.md"].decode("utf-8"),
        )
    )

    assert "does not parse replays" in combined
    assert "HSTuner" in combined
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8").lower()
    assert "candidate promotion" not in operator


def test_active_docs_use_pre_run_boundary_wording():
    embedded = load_embedded_skill_bundle()
    active_docs = {
        "docs/operator/README.md": Path("docs/operator/README.md").read_text(
            encoding="utf-8"
        ),
        "embedded:SKILL.md": embedded["SKILL.md"].decode("utf-8"),
        "embedded:references/workflow.md": embedded[
            "references/workflow.md"
        ].decode("utf-8"),
    }
    required = (
        "HSConfig is pre-run only. It does not parse replays, inspect winrate, "
        "analyze runtime logs, promote candidates, or tune after games."
    )
    missing = [
        path for path, text in active_docs.items() if required not in text
    ]

    assert missing == []
