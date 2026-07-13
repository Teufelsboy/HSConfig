import argparse
import inspect

from hsconfig import package_builder
from hsconfig.commands import source_workflow
from hsconfig.preconfig_context import build_preconfig_context


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _args(tmp_path):
    return argparse.Namespace(
        deck_name="ShadowPriest",
        deck_code=SHADOWPRIEST_CODE,
        out=str(tmp_path / "out"),
        runtime_root=str(tmp_path / "runtime"),
        cards_json=None,
        claims_json=None,
        guide_sources_json=None,
        source_documents_json=None,
        source_evidence_json=None,
        collectible_cards_json=None,
        full_cards_json=None,
        allow_placeholder=False,
        auto_research_fallback=True,
        skip_semantic_fetch=True,
        plan_reports_dir=None,
    )


def test_shared_preconfig_context_contains_prepare_and_research_keys(tmp_path):
    context = build_preconfig_context(_args(tmp_path))

    expected = {
        "cards_payload",
        "deck_identity",
        "card_metadata",
        "semantic_report",
        "guide_claim_bundle",
        "source_claims",
        "research_bundle",
        "guide_sources_generated",
        "guide_builder_receipt",
        "deck_fingerprint",
        "candidate_archetypes",
        "identity_graph_report",
        "identity_gap_report",
        "source_evidence_report",
        "source_document_draft_report",
        "card_data_intake_report",
    }
    assert expected <= set(context)
    assert context["deck_identity"]["deck_name"] == "ShadowPriest"
    assert context["guide_claim_bundle"]["claims"]


def test_research_and_prepare_no_longer_own_duplicate_context_builders():
    source = inspect.getsource(source_workflow)
    package = inspect.getsource(package_builder)

    assert "def _build_research_context(" not in source
    assert "def build_preconfig_context(" not in package
    assert "from hsconfig.preconfig_context import build_preconfig_context" in source
    assert "from hsconfig.preconfig_context import build_preconfig_context" in package
