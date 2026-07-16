import re
from pathlib import Path


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

REQUIRED_DOC_PATHS = (
    Path("docs/operator/source-builder-workflow.md"),
    Path(".agents/skills/hsconfig/references/workflow.md"),
)
REQUIRED_DOC_PHRASES = (
    "hdt_deck_id is identity-only metadata",
    "not replay evidence",
)


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


def test_operator_docs_explain_hdt_as_identity_only():
    missing = []
    for path in REQUIRED_DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        for phrase in REQUIRED_DOC_PHRASES:
            if phrase not in text:
                missing.append(f"{path}:{phrase}")

    assert missing == []


def test_active_docs_keep_hstuner_scope_as_negative_boundary():
    active_docs = [
        Path("README.md"),
        Path("docs/operator/README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_docs)

    assert "does not parse replays" in combined
    assert "HSTuner" in combined
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8").lower()
    assert "candidate promotion" not in operator


def test_active_docs_use_pre_run_boundary_wording():
    active_docs = [
        Path("README.md"),
        Path("docs/operator/README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    required = (
        "HSConfig is pre-run only. It does not parse replays, inspect winrate, "
        "analyze runtime logs, promote candidates, or tune after games."
    )
    missing = [
        str(path)
        for path in active_docs
        if required not in path.read_text(encoding="utf-8")
    ]

    assert missing == []
