"""Unit tests for module entry points."""

from __future__ import annotations

from unittest.mock import patch

import unmouse.__main__ as main_module
from unmouse.main import run_engine_cli


def test_main_runs_launcher_by_default() -> None:
    with patch.object(main_module, "run_launcher") as launcher:
        with patch.object(main_module.sys, "argv", ["unmouse"]):
            main_module.main()
    launcher.assert_called_once()


def test_main_engine_flag_runs_engine() -> None:
    with patch.object(main_module, "run_engine_cli") as engine:
        with patch.object(main_module.sys, "argv", ["unmouse", "--engine"]):
            main_module.main()
    engine.assert_called_once()


def test_main_smoke_flag_runs_smoke_check() -> None:
    with patch.object(main_module, "smoke_check") as smoke:
        with patch.object(main_module.sys, "argv", ["unmouse", "--smoke"]):
            main_module.main()
    smoke.assert_called_once()


def test_smoke_check_prints_version(capsys) -> None:
    main_module.smoke_check()
    output = capsys.readouterr().out
    assert "smoke ok" in output
    assert "1.0.0" in output


def test_engine_entry_delegates_to_run_engine() -> None:
    with patch("unmouse.main.run_engine") as run_engine:
        with patch("unmouse.persistence.load_persisted_settings") as load_settings:
            settings = load_settings.return_value
            run_engine_cli()
    run_engine.assert_called_once_with(settings)
