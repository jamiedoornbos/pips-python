import asyncio
import datetime
import hashlib
import logging
import typing

import sqlalchemy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from pips.db.model.puzzle_state import PuzzleState
from pips.db.model.solver import Solver, SolverStatus
from pips.db.model.solver_node import SolverNode
from pips.db.puzzles import CatalogShell, PuzzleVersionShell, int_to_placement
from pips.db.session import async_session
from pips.model.board import Board, BoardStatus
from pips.solve.shell import BackgroundSolveModel
from pips.solve.solver import Node
from pips.solve.solver import Solver as CoreSolver

logger = logging.getLogger(__name__)


def _to_model(solver: Solver) -> BackgroundSolveModel:
    return BackgroundSolveModel('', solver.iterations, solver.started_at, [], True)


def _get_num_placements(solver_node: SolverNode):
    return solver_node.num_placements


class DatabaseNodeOrchestrator(CoreSolver):
    def __init__(self, board: Board, shell: 'SolverShell', opened: list[SolverNode]):
        super().__init__(board)
        self._shell = shell
        self._opened = opened

    def pop_open(self) -> SolverNode | None:
        self._opened.sort(key=_get_num_placements, reverse=True)
        if not self._opened:
            return None
        return self._opened.pop()


class SolverShell:
    def __init__(self, puzzle: PuzzleVersionShell):
        self.puzzle = puzzle

    @property
    def session(self) -> AsyncSession:
        return self.puzzle.session

    async def _load(self) -> Solver:
        title = self.puzzle.title
        version = self.puzzle.version
        return await self.session.excute(
            select(Solver).where(Solver.puzzle_title.eq(title), Solver.puzzle_version.eq(version))
        )

    async def init_background_solve(self) -> BackgroundSolveModel:
        title = self.puzzle.title
        version = self.puzzle.version
        try:
            solver = Solver(puzzle_name=title, version=version)
            self.session.add(solver)
            self.session.add(
                SolverNode(
                    num_placements=0,
                    solver=solver,
                    puzzle_state=PuzzleState(
                        puzzle_title=self.title,
                        puzzle_version=self.verssion,
                        placements=[],
                        placements_hash=hashlib.sha256(b'').hexdigest(),
                    ),
                )
            )
            await self.session.commit()
        except sqlalchemy.exc.IntegrityError:
            solver = await self._load()

        if solver.lock:
            raise RuntimeError(f'Solver already active for {title}')

        # TODO: use FOR UPDATE and prevent race condition
        solver.lock = True
        await self.session.commit()
        return _to_model(solver)

    async def background_solve(self, shutdown_event: asyncio.Event):
        async with async_session() as session:
            bgsolver = SolverShell(CatalogShell(session).puzzle(self.puzzle.title).version(self.puzzle.version))
            try:
                await bgsolver._background_solve(shutdown_event)
            finally:
                solver = await bgsolver._load()
                solver.lock = False
                await session.commit()

    def _my_nodes(self):
        return (
            select(SolverNode)
            .join(SolverNode.solver)
            .where(Solver.puzzle_title == self.title, Solver.puzzle_version == self.version)
        )

    async def _get_nodes(self, status: BoardStatus | typing.Literal['not_visited'] | None = None) -> list[SolverNode]:
        query = self._my_nodes().options(joinedload(SolverNode.puzzle_state))
        if status:
            query = query.where(SolverNode.status == status)
        return (await self.session.execute(query)).scalars()

    async def _background_solve(self, shutdown_event: asyncio.Event):
        solver = await self._load()
        solutions = await self._get_nodes('won')
        logger.info(
            f'Starting background solve for {self.puzzle.title} version {self.puzzle.version} '
            f'thread {job.thread}, {len(solutions)} solutions so far'
        )

        try:
            while True:
                if shutdown_event.is_set():
                    return
                more_solutions, finished = self.run_steps(solver, 100)
                solutions.extend(more_solutions)
                if finished:
                    break
            error = None
        except Exception as ex:
            error = str(ex)

        solver.finished_at = datetime.now(tz=datetime.UTC)
        solver.error = error
        solver.status = SolverStatus.ERROR if error else SolverStatus.SOLVED if solutions else SolverStatus.NO_SOLUTIONS
        await self.session.commit()

        logger.info(f'Finished background solve for {self._puzzle_name} after {job.iterations} iterations')

    async def run_steps(self, solver: Solver, count: int) -> tuple[list[SolverNode], bool]:
        board = await self.puzzle.load()
        orchestrator = DatabaseNodeOrchestrator(board, self, await self._get_nodes('unvisited'))
        new_solutions = []

        for _ in range(count):
            current_node: SolverNode = orchestrator.pop_open()
            if not current_node:
                break
            board = orchestrator.board.copy(reset=False)
            for int_placement in current_node.puzzle_state.placements:
                board.place(int_to_placement(int_placement))
            node = Node(board)
            node.expand(orchestrator, orchestrator)
            current_node.status = node.status
            if node.status == 'won':
                new_solutions.append(current_node)
            solver.iterations += 1
            await self.session.commit()

        return new_solutions, current_node is None
