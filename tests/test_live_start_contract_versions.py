from __future__ import annotations

import pytest

from hsconfig.starter_contract import live_contract_for_versions


def test_quality_tuple_is_explicit_and_mixed_tuple_fails() -> None:
    values = dict(
        session=2,
        manifest=2,
        context=3,
        candidate=3,
        review=3,
        compiler="hsconfig-live-start-v2",
    )

    assert live_contract_for_versions(**values) == "quality_live"

    with pytest.raises(ValueError, match="live_start_contract_combination_invalid"):
        live_contract_for_versions(**{**values, "review": 2})


def test_legacy_tuple_remains_explicitly_supported() -> None:
    assert live_contract_for_versions(
        session=1,
        manifest=1,
        context=2,
        candidate=2,
        review=2,
        compiler="hsconfig-live-start-v1",
    ) == "legacy_live"


@pytest.mark.parametrize(
    "field",
    ["session", "manifest", "context", "candidate", "review"],
)
def test_boolean_version_is_rejected_as_non_exact_integer(field: str) -> None:
    values: dict[str, object] = {
        "session": 2,
        "manifest": 2,
        "context": 3,
        "candidate": 3,
        "review": 3,
        "compiler": "hsconfig-live-start-v2",
    }
    values[field] = True

    with pytest.raises(ValueError, match="live_start_contract_combination_invalid"):
        live_contract_for_versions(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session", "2"),
        ("manifest", 2.0),
        ("context", None),
        ("candidate", False),
        ("review", object()),
        ("compiler", 2),
    ],
)
def test_non_exact_version_or_compiler_type_is_rejected(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "session": 2,
        "manifest": 2,
        "context": 3,
        "candidate": 3,
        "review": 3,
        "compiler": "hsconfig-live-start-v2",
    }
    values[field] = value

    with pytest.raises(ValueError, match="live_start_contract_combination_invalid"):
        live_contract_for_versions(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "values",
    [
        dict(
            session=9,
            manifest=2,
            context=3,
            candidate=3,
            review=3,
            compiler="hsconfig-live-start-v2",
        ),
        dict(
            session=2,
            manifest=2,
            context=3,
            candidate=3,
            review=3,
            compiler="hsconfig-live-start-v9",
        ),
    ],
)
def test_unknown_version_combination_is_rejected(values: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="live_start_contract_combination_invalid"):
        live_contract_for_versions(**values)  # type: ignore[arg-type]
