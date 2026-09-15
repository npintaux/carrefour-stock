"""Port definition for thermal printer operations.

Traceability:
- [US-4][AC-4.1]: ESC/POS label printing port.
"""

from __future__ import annotations

import abc

from ..models import LabelPrintCommand


class PrinterPort(abc.ABC):
    """Abstract port for ESC/POS promotional label generation and printing."""

    @abc.abstractmethod
    def print_label(
        self,
        request_id: str,
        evaluation_id: str,
        ean_barcode: str,
        discounted_price_cents: int,
        quantity: int,
        printer_id: str,
    ) -> LabelPrintCommand:
        """Generate thermal print instructions and barcode.

        Args:
            request_id: Unique request identifier.
            evaluation_id: Associated evaluation ID.
            ean_barcode: Product EAN-13 barcode.
            discounted_price_cents: Discounted unit price in cents.
            quantity: Number of labels to print.
            printer_id: Target printer identifier.

        Returns:
            LabelPrintCommand with promotional barcode and ESC/POS payload.
        """
        ...
