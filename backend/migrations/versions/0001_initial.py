"""Initial research workspace tables."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('patients', sa.Column('id',sa.String(),primary_key=True),sa.Column('data',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('trials', sa.Column('id',sa.String(),primary_key=True),sa.Column('data',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('match_runs', sa.Column('id',sa.String(),primary_key=True),sa.Column('patient_id',sa.String(),nullable=False),sa.Column('data',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_match_runs_patient_id','match_runs',['patient_id'])


def downgrade():
    op.drop_table('match_runs')
    op.drop_table('trials')
    op.drop_table('patients')
