import argparse
import inspect

from hsconfig import package_builder
from hsconfig.commands import source_workflow
from hsconfig import preconfig_context
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


def test_research_contract_payload_does_not_fetch_collectible_cards_without_local_feed(
    tmp_path, monkeypatch
):
    collectible_fetch_calls = []

    def fail_if_called(timeout=10.0):
        collectible_fetch_calls.append(timeout)
        return []

    monkeypatch.setitem(
        preconfig_context.build_preconfig_context.__kwdefaults__,
        "fetch_latest_collectible_cards_fn",
        fail_if_called,
    )
    monkeypatch.setattr(package_builder, "fetch_latest_cards", lambda timeout=10.0: [])

    args = _args(tmp_path)
    args.skip_semantic_fetch = False

    payload, exit_code = package_builder.research_contract_payload(args)

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert collectible_fetch_calls == []
