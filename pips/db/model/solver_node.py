from sqlalchemy import BigInteger, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pips.db.model._base import Base
from pips.db.model.puzzle_state import PuzzleState
from pips.db.model.solver import Solver


class SolverNode(Base):
    __tablename__ = 'solver_node'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    num_placements: Mapped[int] = mapped_column(Integer, nullable=False)
    solver_id: Mapped[int] = mapped_column(ForeignKey(Solver.id), nullable=False)
    puzzle_state_id: Mapped[int] = mapped_column(ForeignKey(PuzzleState.id), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default='unvisited')

    solver: Mapped[Solver] = relationship(Solver)
    puzzle_state: Mapped[PuzzleState] = relationship(PuzzleState)

    __table_args__ = (UniqueConstraint(solver_id, puzzle_state_id),)
