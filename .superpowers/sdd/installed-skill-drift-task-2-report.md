Status: DONE_WITH_CONCERNS

Date: 2026-07-22

Summary:
- Task 2 implementation is already present at `HEAD` in commit `dc77192ffeec51f6e44f45d82fee9d64bca26d7e` (`feat: expose installed skill sync in contract preflight`).
- Owned files from the brief already contain the requested installed-skill sync plumbing, CLI flag, command-wrapper fallback, and tests.
- This pass verified the existing implementation and recorded the results.

Commits:
- `dc77192ffeec51f6e44f45d82fee9d64bca26d7e` - `feat: expose installed skill sync in contract preflight`
- Task 1 dependency already present from `e81edcb` - `feat: share installed skill sync status`

Files changed:
- No source changes were required in this turn.
- Added report: `.superpowers/sdd/installed-skill-drift-task-2-report.md`

RED result:
- Command run:
  - `python -m pytest tests/test_contract_preflight.py::test_contract_preflight_reports_installed_skill_sync_when_clean tests/test_contract_preflight.py::test_contract_preflight_reports_attention_when_installed_skill_drifts -q`
- Actual result:
  - `2 passed in 0.24s`
- Interpretation:
  - The expected RED failure from the brief was not reproducible because `build_contract_preflight(..., skill_install_root=...)` and the installed-skill sync payload were already implemented at `HEAD` before this turn started.

GREEN result:
- Command run:
  - `python -m pytest tests/test_contract_preflight.py tests/test_skill_sync.py -q`
- Result:
  - `20 passed in 5.29s`

Concerns:
- The brief-required RED step could not be observed in this workspace because Task 2 had already landed before this turn.
- No new Task 2 code commit was created in this turn for the same reason; the existing Task 2 commit at `HEAD` already matches the required message.

git status --short --branch:
```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring [ahead 3]
```

---

Status: FIXED

Date: 2026-07-22

Summary:
- Fixed the `installed_skill_sync` exception-path fallback so `installed_skill_path` honors a caller-provided `--skill-install-root`.
- Added a focused regression that forces `build_installed_skill_sync_status()` to raise and verifies the fallback payload resolves to `<install_root>/hsconfig`.
- Verified the new fallback path via RED/GREEN and documented the broader suite behavior while the worktree was dirty during the patch.

Files changed:
- `src/hsconfig/commands/contract_preflight.py`
- `tests/test_contract_preflight.py`

RED result:
- Command run:
  - `python -m pytest tests/test_contract_preflight.py::test_unavailable_installed_skill_payload_preserves_install_root_override -q`
- Result:
```text
F                                                                        [100%]
================================== FAILURES ===================================
__ test_unavailable_installed_skill_payload_preserves_install_root_override ___

tmp_path = WindowsPath('C:/Users/darbo/AppData/Local/Temp/pytest-of-darbo/pytest-5396/test_unavailable_installed_ski0')
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x0000019C61CE10D0>

    def test_unavailable_installed_skill_payload_preserves_install_root_override(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        install_root = tmp_path / "custom-skills"
    
        def _raise_sync_error(repo_root: str, passed_install_root: object) -> dict[str, object]:
            raise RuntimeError(f"boom: {repo_root} / {passed_install_root}")
    
        monkeypatch.setattr(
            contract_preflight_command,
            "build_installed_skill_sync_status",
            _raise_sync_error,
        )
    
        payload = contract_preflight_command._unavailable_installed_skill_payload(
            ".",
            install_root,
        )
    
>       assert payload["installed_skill_path"] == str(install_root / "hsconfig")
E       AssertionError: assert 'C:\\Users\\d...lls\\hsconfig' == 'C:\\Users\\d...lls\\hsconfig'
E         
E         - C:\Users\darbo\AppData\Local\Temp\pytest-of-darbo\pytest-5396\test_unavailable_installed_ski0\custom-skills\hsconfig
E         + C:\Users\darbo\.codex\skills\hsconfig

tests\test_contract_preflight.py:319: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_contract_preflight.py::test_unavailable_installed_skill_payload_preserves_install_root_override
1 failed in 0.33s
```

GREEN result:
- Focused regression command:
  - `python -m pytest tests/test_contract_preflight.py::test_unavailable_installed_skill_payload_preserves_install_root_override -q`
- Result:
```text
.                                                                        [100%]
1 passed in 0.11s
```

Requested suite result before commit:
- Command run:
  - `python -m pytest tests/test_contract_preflight.py tests/test_skill_sync.py -q`
- Result:
```text
........F............                                                    [100%]
================================== FAILURES ===================================
___ test_contract_preflight_cli_reports_installed_skill_sync_without_writes ___

tmp_path = WindowsPath('C:/Users/darbo/AppData/Local/Temp/pytest-of-darbo/pytest-5398/test_contract_preflight_cli_re1')

    def test_contract_preflight_cli_reports_installed_skill_sync_without_writes(
        tmp_path: Path,
    ) -> None:
[...]
>       assert result.returncode == 0
E       assert 1 == 0
E        +  where 1 = CompletedProcess(...).returncode

tests\test_contract_preflight.py:292: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_contract_preflight.py::test_contract_preflight_cli_reports_installed_skill_sync_without_writes
1 failed, 20 passed in 5.26s
```

Dirty-tree diagnosis:
- Command run:
  - `python -m hsconfig.cli contract-preflight --repo-root . --skill-install-root C:\Users\darbo\AppData\Local\Temp\pytest-of-darbo\pytest-5398\test_contract_preflight_cli_re1\codex\skills --json`
- Key result:
  - `installed_skill_sync_current=true`
  - `installed_skill_path=C:\Users\darbo\AppData\Local\Temp\pytest-of-darbo\pytest-5398\test_contract_preflight_cli_re1\codex\skills\hsconfig`
  - `status=ATTENTION` only because `repo_current=false` and `git.dirty=true` while the patch was uncommitted.

Post-commit verification:
- Command run:
  - `python -m pytest tests/test_contract_preflight.py tests/test_skill_sync.py -q`
- Result:
```text
.....................                                                    [100%]
21 passed in 4.97s
```

Commit:
- `a8d29a73278731bce3b3fba18c5731fb85f00008` - `fix: preserve install root in preflight fallback`

Final git status --short --branch:
```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring [ahead 4]
```

---

Status: FIXED

Date: 2026-07-22

Summary:
- Narrowed the Task 2 re-review fix to the owned contract-preflight wrapper and its tests.
- Brought the exception-path installed-skill fallback into line with `hsconfig.skill_sync_status` by reusing `DEFAULT_INSTALL_ROOT` and `Path(install_root).expanduser()` semantics.
- Relaxed the live CLI test so it still verifies installed-skill sync and no-write behavior even when unrelated repo-currentness checks return `ATTENTION`.

Files changed:
- `src/hsconfig/commands/contract_preflight.py`
- `tests/test_contract_preflight.py`
- `.superpowers/sdd/installed-skill-drift-task-2-report.md`

RED result:
- Command run:
  - `python -m pytest tests/test_contract_preflight.py -q -k "tilde_install_root_override or installed_skill_sync_without_writes"`
- Result:
```text
.F                                                                       [100%]
================================== FAILURES ===================================
_ test_unavailable_installed_skill_payload_expands_tilde_install_root_override _

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x00000292BDAF5A10>

    def test_unavailable_installed_skill_payload_expands_tilde_install_root_override(
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        install_root = "~/.codex/custom-skills"

        def _raise_sync_error(repo_root: str, passed_install_root: object) -> dict[str, object]:
            raise RuntimeError(f"boom: {repo_root} / {passed_install_root}")

        monkeypatch.setattr(
            contract_preflight_command,
            "build_installed_skill_sync_status",
            _raise_sync_error,
        )

        payload = contract_preflight_command._unavailable_installed_skill_payload(
            ".",
            install_root,
        )

>       assert payload["installed_skill_path"] == str(
            Path(install_root).expanduser() / "hsconfig"
        )
E       AssertionError: assert 'C:\\Users\\d...lls\\hsconfig' == 'C:\\Users\\d...lls\\hsconfig'
E
E         - C:\Users\darbo\.codex\custom-skills\hsconfig
E         + C:\Users\darbo\Documents\HSConfig\~\.codex\custom-skills\hsconfig
E         ?               +++++++++++++++++++++

tests\test_contract_preflight.py:318: AssertionError
=========================== short test summary info ============================
FAILED tests/test_contract_preflight.py::test_unavailable_installed_skill_payload_expands_tilde_install_root_override
1 failed, 1 passed, 13 deselected in 1.05s
```

Focused GREEN result:
- Command run:
  - `python -m pytest tests/test_contract_preflight.py -q -k "tilde_install_root_override or installed_skill_sync_without_writes"`
- Result:
```text
..                                                                       [100%]
2 passed, 13 deselected in 1.20s
```

Requested suite result:
- Command run:
  - `python -m pytest tests/test_contract_preflight.py tests/test_skill_sync.py -q`
- Result:
```text
.....................                                                    [100%]
21 passed in 5.48s
```

Commit message:
- `fix: harden installed skill preflight fallback`

Final git status --short --branch:
```text
## codex/hsconfig-semantic-intent-scoring...origin/codex/hsconfig-semantic-intent-scoring [ahead 5]
```
