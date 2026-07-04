import asyncio
import datetime
import logging
import typing

import sqlalchemy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from pips.app.models import PlacementModel
from pips.db.model.puzzle_state import PuzzleState
from pips.db.model.solver import Solver, SolverStatus
from pips.db.model.solver_node import SolverNode
from pips.db.puzzles import CatalogShell, PuzzleVersionShell, int_to_placement
from pips.db.session import async_session
from pips.model.board import Board, BoardStatus
from pips.model.placement import Placement
from pips.solve.shell import BackgroundSolveModel, SolverResultModel
from pips.solve.solver import Node
from pips.solve.solver import Solver as CoreSolver

logger = logging.getLogger(__name__)


def _to_model(solver: Solver) -> BackgroundSolveModel:
    # TODO: redo the outbound models
    return BackgroundSolveModel(
        thread='', iterations=solver.iterations, start_time=solver.started_at, output=[], is_running=True
    )


def _get_num_placements(solver_node: SolverNode):
    return solver_node.num_placements


class DatabaseNodeOrchestrator(CoreSolver):
    def __init__(self, board: Board, shell: PuzzleVersionShell, solver: Solver, opened: list[SolverNode]):
        super().__init__(board)
        self._shell = shell
        self._opened = opened
        self._solver = solver

    def pop_open(self) -> SolverNode | None:
        self._opened.sort(key=_get_num_placements, reverse=True)
        if not self._opened:
            return None
        return self._opened.pop()

    async def add_node_async(self, parent: Node, placement: Placement):
        session = self._shell.session
        state_id, _state_existed = await self._shell.upsert_board(parent.board, placement)
        query = select(SolverNode).where(SolverNode.puzzle_state_id == state_id)

        # TODO: use postgres dialect upsert for 1 round trip instead of 2
        if node := (await session.execute(query)).scalars().first():
            return node.status, True

        puzzle_state = await session.get(PuzzleState, state_id)
        session.add(
            node := SolverNode(
                num_placements=len(parent.board.placements) + 1,
                solver=self._solver,
                puzzle_state=puzzle_state,
            )
        )
        await session.commit()
        self._opened.append(node)
        return node.status, False


class SolverShell:
    def __init__(self, puzzle: PuzzleVersionShell):
        self.puzzle = puzzle

    @property
    def session(self) -> AsyncSession:
        return self.puzzle.session

    @property
    def title(self) -> str:
        return self.puzzle.title

    @property
    def version(self) -> int:
        return self.puzzle.version

    async def get_result(self) -> SolverResultModel | None:
        solver = await self.load()
        if solver.status != SolverStatus.SOLVED:
            return None

        solutions = []
        for solution in await self._get_nodes('won'):
            solutions.append(
                [
                    PlacementModel(domino=placement.domino, loc=placement.pos.loc, dir=placement.pos.dir.value.name)
                    for placement in [int_to_placement(pl) for pl in solution.puzzle_state.placements]
                ]
            )

        return SolverResultModel(
            puzzle_name=self.title,
            peak_memory_usage_mb=0,
            iterations=solver.iterations,
            time_to_solve=solver.finished_at - solver.started_at,
            completion_time=solver.finished_at,
            error=solver.error,
            solutions=solutions,
        )

    async def load(self) -> Solver:
        title = self.puzzle.title
        version = self.puzzle.version
        return (
            (
                await self.session.execute(
                    select(Solver).where(Solver.puzzle_title == title, Solver.puzzle_version == version)
                )
            )
            .scalars()
            .first()
        )

    async def init_solver(self) -> BackgroundSolveModel:
        title = self.puzzle.title
        version = self.puzzle.version
        state_id, _existed = await self.puzzle.upsert_board(await self.puzzle.load())
        try:
            self.session.add_all(
                [
                    solver := Solver(puzzle_title=title, puzzle_version=version),
                    SolverNode(
                        num_placements=0,
                        solver=solver,
                        puzzle_state_id=state_id,
                    ),
                ]
            )
            await self.session.flush()
        except sqlalchemy.exc.IntegrityError:
            await self.session.rollback()
            solver = await self.load()

        if solver.lock:
            raise RuntimeError(f'Solver already active for {title}')

        await self.session.commit()
        return _to_model(solver)

    async def solve(self, cancel_event: asyncio.Event):
        try:
            solver = await self.load()

            if solver.lock:
                raise RuntimeError(f'Solver already active for {self.title}')

            # TODO: use FOR UPDATE and prevent race condition
            solver.lock = True
            await self.session.commit()

            solutions = await self._get_nodes('won')
            logger.info(
                f'Starting background solve for {self.title} version {self.version} {len(solutions)} solutions so far'
            )

            try:
                while True:
                    if cancel_event.is_set():
                        return
                    more_solutions, finished = await self.run_steps(solver, cancel_event, 100)
                    solutions.extend(more_solutions)
                    if finished:
                        break
                error = None
            except Exception as ex:
                error = str(ex)

            solver.finished_at = datetime.datetime.now(tz=datetime.UTC)
            solver.error = error
            solver.status = (
                SolverStatus.ERROR if error else SolverStatus.SOLVED if solutions else SolverStatus.NO_SOLUTIONS
            )
            await self.session.commit()

            logger.info(f'Finished background solve for {self.title} after {solver.iterations} iterations')
        except:
            self.session.rollback()
            raise
        finally:
            solver = await self.load()
            solver.lock = False
            await self.session.commit()

    async def background_solve(self, cancel_event: asyncio.Event):
        # the self session will close, fire up a new one for the background
        async with async_session() as session:
            shell = SolverShell(CatalogShell(session).puzzle(self.puzzle.title).version(self.puzzle.version))
            await shell.solve(cancel_event)

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
        return (await self.session.execute(query)).scalars().all()

    async def run_steps(self, solver: Solver, cancel_event: asyncio.Event, count: int) -> tuple[list[SolverNode], bool]:
        board = await self.puzzle.load()
        orchestrator = DatabaseNodeOrchestrator(board, self.puzzle, solver, await self._get_nodes('unvisited'))
        new_solutions = []

        for _ in range(count):
            current_node: SolverNode = orchestrator.pop_open()
            if not current_node or cancel_event.is_set():
                break
            board = orchestrator.board.copy(reset=False)
            for int_placement in current_node.puzzle_state.placements:
                board.place(int_to_placement(int_placement))
            node = Node(board)
            await node.expand_async(orchestrator, orchestrator)
            current_node.status = node.status
            if node.status == 'won':
                new_solutions.append(current_node)
            solver.iterations += 1
            await self.session.commit()

        return new_solutions, current_node is None
