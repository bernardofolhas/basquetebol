"""Establishes the Alembic baseline for existing installations.

The project predates Alembic and currently creates the ORM schema at startup,
with a small compatibility updater for legacy databases. This revision is
intentionally empty: it records the point from which future schema changes
must be delivered as explicit migrations without trying to rebuild or alter a
live club database during Phase 0.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Mark the existing ORM-managed schema as the migration baseline."""


def downgrade() -> None:
    """Keep the baseline irreversible to avoid deleting club data."""

