"""Unit tests for ColdChainEvaluator."""

from __future__ import annotations

import pytest

from src.modules.inbound_dock.domain.cold_chain_evaluator import ColdChainEvaluator
from src.modules.inbound_dock.domain.exceptions import (
    ColdChainViolationError,
    MissingTemperatureError,
)
from src.modules.inbound_dock.domain.models import TemperatureRegime


def test_us3_ac3_1_ambient_evaluation() -> None:
    """[US-3][AC-3.1] Ambient regime requires no temperature probe."""
    evaluator = ColdChainEvaluator()
    is_compliant, reason = evaluator.evaluate(TemperatureRegime.AMBIENT, None)
    assert is_compliant is True
    assert reason is None

    is_compliant2, reason2 = evaluator.evaluate(TemperatureRegime.AMBIENT, 25.0)
    assert is_compliant2 is True
    assert reason2 is None


def test_us3_ac3_1_chilled_evaluation() -> None:
    """[US-3][AC-3.1] Chilled regime requires 0.0°C <= T <= 4.0°C."""
    evaluator = ColdChainEvaluator()

    # Missing probe
    with pytest.raises(MissingTemperatureError, match="Missing probed temperature"):
        evaluator.evaluate(TemperatureRegime.CHILLED, None)

    # Compliant temperatures
    for temp in [0.0, 2.5, 4.0]:
        is_compliant, reason = evaluator.evaluate(TemperatureRegime.CHILLED, temp)
        assert is_compliant is True
        assert reason is None

    # Below 0.0°C
    is_compliant, reason = evaluator.evaluate(TemperatureRegime.CHILLED, -1.5)
    assert is_compliant is False
    assert reason == "COLD_CHAIN_VIOLATION"

    # Above 4.0°C
    is_compliant, reason = evaluator.evaluate(TemperatureRegime.CHILLED, 7.5)
    assert is_compliant is False
    assert reason == "COLD_CHAIN_VIOLATION"


def test_us3_ac3_1_frozen_evaluation() -> None:
    """[US-3][AC-3.1] Frozen regime requires T <= -18.0°C."""
    evaluator = ColdChainEvaluator()

    # Missing probe
    with pytest.raises(MissingTemperatureError, match="Missing probed temperature"):
        evaluator.evaluate(TemperatureRegime.FROZEN, None)

    # Compliant temperatures
    for temp in [-18.0, -22.5]:
        is_compliant, reason = evaluator.evaluate(TemperatureRegime.FROZEN, temp)
        assert is_compliant is True
        assert reason is None

    # Above -18.0°C
    is_compliant, reason = evaluator.evaluate(TemperatureRegime.FROZEN, -15.0)
    assert is_compliant is False
    assert reason == "COLD_CHAIN_VIOLATION"


def test_us3_ac3_1_assert_compliance_helper() -> None:
    """[US-3][AC-3.1] Verify assert_compliance helper raises ColdChainViolationError on breach."""
    evaluator = ColdChainEvaluator()
    evaluator.assert_compliance(TemperatureRegime.CHILLED, 2.0)

    with pytest.raises(
        ColdChainViolationError, match="Cold-chain temperature out of compliance"
    ):
        evaluator.assert_compliance(TemperatureRegime.CHILLED, 8.0)
