"""Cold-chain regulatory temperature evaluation component."""

from __future__ import annotations

from .exceptions import ColdChainViolationError, MissingTemperatureError
from .models import TemperatureRegime


class ColdChainEvaluator:
    """Evaluates probed temperatures against regulatory thresholds for perishable regimes."""

    def evaluate(
        self, regime: TemperatureRegime, probed_temperature: float | None
    ) -> tuple[bool, str | None]:
        """Evaluate probed temperature compliance against regime requirements.

        Args:
            regime: Temperature regime of the pallet (AMBIENT, CHILLED, FROZEN).
            probed_temperature: Probed temperature reading in °C, or None.

        Returns:
            Tuple of (is_compliant, violation_reason).

        Raises:
            MissingTemperatureError: If probed_temperature is omitted for CHILLED or FROZEN.
        """
        if regime == TemperatureRegime.AMBIENT:
            return True, None

        if probed_temperature is None:
            raise MissingTemperatureError(
                f"Missing probed temperature reading for {regime.value} pallet"
            )

        if regime == TemperatureRegime.CHILLED:
            if 0.0 <= probed_temperature <= 4.0:
                return True, None
            return False, "COLD_CHAIN_VIOLATION"

        if regime == TemperatureRegime.FROZEN:
            if probed_temperature <= -18.0:
                return True, None
            return False, "COLD_CHAIN_VIOLATION"

        return False, "UNKNOWN_REGIME"

    def assert_compliance(
        self, regime: TemperatureRegime, probed_temperature: float | None
    ) -> None:
        """Assert that probed temperature complies with regime, raising on breach.

        Args:
            regime: Temperature regime of the pallet.
            probed_temperature: Probed temperature reading in °C.

        Raises:
            ColdChainViolationError: If temperature is out of compliance.
            MissingTemperatureError: If probed_temperature is missing for cold regimes.
        """
        is_compliant, reason = self.evaluate(regime, probed_temperature)
        if not is_compliant:
            raise ColdChainViolationError(
                f"Cold-chain temperature out of compliance: {probed_temperature}°C "
                f"for regime {regime.value} ({reason})"
            )
