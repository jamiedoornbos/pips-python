import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from pips.db.model._base import Base
from pips.db.model.puzzle import Puzzle


class SolverStatus(enum.Enum):
    NOT_RUN = 'not_run'
    NO_SOLUTIONS = 'no_solutions'
    ERROR = 'error'
    SOLVED = 'solved'


class Solver(Base):
    __tablename__ = 'solver'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    puzzle_title: Mapped[str] = mapped_column(Text, nullable=False)
    puzzle_version: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String)
    peak_memory_usage_mb: Mapped[float | None] = mapped_column(Float)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[SolverStatus] = mapped_column(Enum(SolverStatus, native_enum=False), default='not_run')
    lock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    puzzle: Mapped[Puzzle] = relationship(Puzzle, back_populates='solver')

    __table_args__ = (
        ForeignKeyConstraint([puzzle_title, puzzle_version], [Puzzle.title, Puzzle.version]),
        UniqueConstraint(puzzle_title, puzzle_version),
    )
