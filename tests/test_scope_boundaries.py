from pathlib import Path


FORBIDDEN_SRC_TERMS = {
    "power.log",
    "hsreplay",
    "hdt replay",
    "winrate",
    "candidate promotion",
    "post-run tuning",
    "analyze-step2",
}


def test_hsconfig_src_does_not_absorb_post_run_scope():
    offenders = []
    for path in sorted(Path("src/hsconfig").glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_SRC_TERMS:
            if term in text:
                offenders.append(f"{path}:{term}")

    assert offenders == []


def test_operator_docs_explain_hdt_as_identity_only():
    docs = (
        Path("docs/operator/source-builder-workflow.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/references/workflow.md").read_text(
            encoding="utf-8"
        )
    )

    assert "hdt_deck_id is identity-only metadata" in docs
    assert "not replay evidence" in docs
