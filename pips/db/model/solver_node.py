import enum

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pips.db.model._base import Base
from pips.db.model.puzzle_state import PuzzleState
from pips.db.model.solver import Solver


class SolverNodeStatus(enum.Enum):
    WON = 'won'
    LOST = 'lost'
    INCOMPLETE = 'incomplete'
    UNVISITED = 'unvisited'


class SolverNode(Base):
    __tablename__ = 'solver_node'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    num_placements: Mapped[int] = mapped_column(Integer, nullable=False)
    solver_id: Mapped[int] = mapped_column(ForeignKey(Solver.id, ondelete='cascade'), nullable=False)
    puzzle_state_id: Mapped[int] = mapped_column(ForeignKey(PuzzleState.id), nullable=False)
    status: Mapped[SolverNodeStatus] = mapped_column(
        Enum(SolverNodeStatus, native_enum=False), default=SolverNodeStatus.UNVISITED
    )

    solver: Mapped[Solver] = relationship(Solver)
    puzzle_state: Mapped[PuzzleState] = relationship(PuzzleState)

    __table_args__ = (UniqueConstraint(solver_id, puzzle_state_id),)
