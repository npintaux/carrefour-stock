"""In-memory thermal printer adapter generating mock ESC/POS streams and barcodes.

Traceability:
- [US-4][AC-4.1]: Mobile Bluetooth ESC/POS print command generation.
"""

from __future__ import annotations

import base64
import uuid

from ..domain.exceptions import PrinterCommunicationError
from ..domain.models import LabelPrintCommand
from ..domain.ports.printer_port import PrinterPort


class InMemoryPrinterAdapter(PrinterPort):
    """In-memory printer port adapter for promotional barcode and ESC/POS generation."""

    def __init__(self, simulate_fault: bool = False) -> None:
        """Initialize adapter.

        Args:
            simulate_fault: When True, simulates printer connection failure.
        """
        self.simulate_fault = simulate_fault

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

        Raises:
            PrinterCommunicationError: If simulate_fault is active.
        """
        if self.simulate_fault:
            raise PrinterCommunicationError(
                f"Printer hardware communication failed for printer '{printer_id}'."
            )

        job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        # Build 13-digit promotional barcode: prefix '29' + 5 digits price + 5 digits ean suffix + check
        ean_suffix = ean_barcode[-5:] if len(ean_barcode) >= 5 else "00000"
        price_padded = f"{discounted_price_cents:05d}"
        promotional_barcode = f"29{price_padded[:4]}{ean_suffix[:6]}1"[:13]

        # Simple synthetic ESC/POS command stream: ESC @ (init), text, GS V (cut)
        raw_bytes = (
            b"\x1b@"  # ESC @ initialize printer
            + b"CARREFOUR DATE COURTE\n"
            + f"PRIX: {discounted_price_cents / 100:.2f} EUR\n".encode("ascii")
            + f"CODE: {promotional_barcode}\n".encode("ascii")
            + b"\x1dV\x00"  # GS V 0 full cut
        )
        escpos_base64 = base64.b64encode(raw_bytes).decode("ascii")

        return LabelPrintCommand(
            job_id=job_id,
            promotional_barcode=promotional_barcode,
            escpos_payload_base64=escpos_base64,
            labels_printed=quantity,
        )
