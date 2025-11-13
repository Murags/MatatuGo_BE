"""Add node_id to stages and link it to edges for pgRouting

Revision ID: 5a431c218b67
Revises: f82cde9a7fa4
Create Date: 2025-11-02 13:53:07.246062
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers
revision = '5a431c218b67'
down_revision = 'f82cde9a7fa4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1️⃣ Add node_id (temporarily nullable)
    op.add_column("stages", sa.Column("node_id", sa.Integer(), nullable=True))

    # 2️⃣ Populate node_id with sequential integers
    conn.execute(text("""
        UPDATE stages s
        SET node_id = sub.new_id
        FROM (
            SELECT stop_id, ROW_NUMBER() OVER (ORDER BY stop_id) AS new_id
            FROM stages
        ) sub
        WHERE s.stop_id = sub.stop_id;
    """))

    # 3️⃣ Ensure all values assigned
    remaining = conn.execute(text("""
        SELECT COUNT(*) FROM stages WHERE node_id IS NULL
    """)).scalar()

    if remaining > 0:
        raise Exception(f"❌ Failed: {remaining} rows missing node_id")

    # 4️⃣ Drop old primary key + FKs depending on it
    op.drop_constraint("stop_times_stop_id_fkey", "stop_times", type_="foreignkey")
    op.drop_constraint("transfers_from_stop_id_fkey", "transfers", type_="foreignkey")
    op.drop_constraint("transfers_to_stop_id_fkey", "transfers", type_="foreignkey")
    op.drop_constraint("stages_pkey", "stages", type_="primary")

    # 5️⃣ Make node_id the new PRIMARY KEY
    # op.create_primary_key("stages_pkey", "stages", ["node_id"])
    op.create_primary_key("stages_pkey", "stages", ["node_id"])

    # ✅ Required: stop_id must stay unique for foreign key references
    op.create_unique_constraint("stages_stop_id_key", "stages", ["stop_id"])


    # 6️⃣ Recreate foreign keys back (still via stop_id)
    op.create_foreign_key(
        "stop_times_stop_id_fkey", "stop_times", "stages",
        local_cols=["stop_id"], remote_cols=["stop_id"]
    )
    op.create_foreign_key(
        "transfers_from_stop_id_fkey", "transfers", "stages",
        local_cols=["from_stop_id"], remote_cols=["stop_id"]
    )
    op.create_foreign_key(
        "transfers_to_stop_id_fkey", "transfers", "stages",
        local_cols=["to_stop_id"], remote_cols=["stop_id"]
    )

    # 7️⃣ Add source_id + target_id to edges (nullable for now)
    op.add_column("edges", sa.Column("source_id", sa.Integer(), nullable=True))
    op.add_column("edges", sa.Column("target_id", sa.Integer(), nullable=True))

    # 8️⃣ Populate source/target from stop_id mapping
    conn.execute(text("""
        UPDATE edges e
        SET source_id = s.node_id
        FROM stages s
        WHERE e.source = s.stop_id;
    """))

    conn.execute(text("""
        UPDATE edges e
        SET target_id = s.node_id
        FROM stages s
        WHERE e.target = s.stop_id;
    """))

    # 9️⃣ Verify mapping success
    missing = conn.execute(text("""
        SELECT COUNT(*) FROM edges WHERE source_id IS NULL OR target_id IS NULL
    """)).scalar()

    if missing > 0:
        raise Exception(f"❌ Failed: {missing} edges missing node references")

    # 10️⃣ Enforce NOT NULL (only now!)
    op.alter_column("edges", "source_id", nullable=False)
    op.alter_column("edges", "target_id", nullable=False)

    print("\n✅ node_id added & edges linked — Routing Ready!\n")


def downgrade():
    conn = op.get_bind()

    # Drop keys/constraints in reverse order
    op.drop_constraint("stages_pkey", "stages", type_="primary")

    op.drop_constraint("stop_times_stop_id_fkey", "stop_times", type_="foreignkey")
    op.drop_constraint("transfers_from_stop_id_fkey", "transfers", type_="foreignkey")
    op.drop_constraint("transfers_to_stop_id_fkey", "transfers", type_="foreignkey")

    op.drop_column("edges", "target_id")
    op.drop_column("edges", "source_id")

    op.drop_column("stages", "node_id")
