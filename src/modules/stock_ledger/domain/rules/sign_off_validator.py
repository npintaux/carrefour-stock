"""Validator for director sign-off operations (S1)."""

from __future__ import annotations

from ..exceptions import (
    AdjustmentNotFoundError,
    InvalidPayloadError,
    InvalidTransitionError,
    UnauthorizedDirectorError,
)
from ..models import AdjustmentRecord, AdjustmentStatus


class SignOffValidator:
    """Validates director sign-off requests for high-value write-offs."""

    def validate(
        self,
        record: AdjustmentRecord | None,
        director_id: str,
        director_role: str,
        action: str,
        note: str | None,
    ) -> bool:
        """Validate whether the director sign-off request is permissible.

        Args:
            record: The target AdjustmentRecord entity if found, or None.
            director_id: User identifier of the director.
            director_role: Role claim of the director.
            action: Action requested ('APPROVE' or 'REJECT').
            note: Justification note from the director.

        Returns:
            True if valid.

        Raises:
            AdjustmentNotFoundError: If record is None.
            UnauthorizedDirectorError: If director_role is not DIRECTEUR_MAGASIN.
            InvalidTransitionError: If record is not in PENDING_DIRECTOR_APPROVAL status.
            InvalidPayloadError: If action is invalid or REJECT has no non-empty note.
        """
        if record is None:
            raise AdjustmentNotFoundError("Adjustment record not found.")

        if director_role != "DIRECTEUR_MAGASIN":
            raise UnauthorizedDirectorError(
                "User lacks DIRECTEUR_MAGASIN authorization to sign off."
            )

        if action not in ("APPROVE", "REJECT"):
            raise InvalidPayloadError(
                f"Action must be APPROVE or REJECT, got: {action}."
            )

        if action == "REJECT" and (note is None or not note.strip()):
            raise InvalidPayloadError(
                "Mandatory justification note required when rejecting an adjustment."
            )

        if record.status != AdjustmentStatus.PENDING_DIRECTOR_APPROVAL:
            raise InvalidTransitionError(
                f"Adjustment '{record.adjustment_id}' is in state {record.status.value}, "
                "not PENDING_DIRECTOR_APPROVAL."
            )

        return True
