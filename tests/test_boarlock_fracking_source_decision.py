from __future__ import annotations

import json
from pathlib import Path


DECISION_DOC = Path("docs/operator/boarlock-fracking-source-decision.md")
BOARLOCK_FIXTURE = Path("tests/fixtures/source_documents_boarlock_strong.json")


def test_boarlock_fracking_decision_artifact_exists_and_sets_boundary():
    text = DECISION_DOC.read_text(encoding="utf-8")

    assert "# Boarlock Fracking Source Decision" in text
    assert "`WW_092` / `Fracking`" in text
    assert "`exact_boarlock_fracking_mulligan_source_unavailable`" in text
    assert "Low-confidence generic card-draw advice is not enough" in text
    assert "Adjacent archetype advice is not enough" in text
    assert "Do not promote Boarlock to `core_source_backed_fixture`" in text
    assert "Next actionable closure target: `Kingslayer`" in text


def test_existing_fracking_mulligan_claim_is_low_confidence_only():
    payload = json.loads(BOARLOCK_FIXTURE.read_text(encoding="utf-8"))
    claims = [
        claim
        for source in payload["source_documents"]
        for claim in source["claims"]
        if claim.get("claim_kind") == "mulligan_keep"
        and "WW_092" in claim.get("cards", [])
    ]

    assert len(claims) == 1
    assert claims[0]["source_confidence"] == "low"
    assert "card draw" in claims[0]["evidence_text_short"].lower()
