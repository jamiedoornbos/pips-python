import asyncio
import datetime
import logging
import typing

import sqlalchemy
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from pips.app.models import PlacementModel
from pips.db.model.solver import Solver, SolverStatus
from pips.db.model.solver_node import SolverNode
from pips.db.puzzles import CatalogShell, PuzzleVersionShell, bytes_to_placements, int_to_placement
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


def _get_num_placements(entry: tuple[SolverNode, list[Placement]]):
    return entry[0].num_placements


class DatabaseNodeOrchestrator(CoreSolver):
    def __init__(self, board: Board, shell: PuzzleVersionShell, solver: Solver, opened: list[SolverNode]):
        super().__init__(board)
        self._shell = shell
        self._opened: list[tuple[SolverNode, list[Placement]]] = [
            (node, bytes_to_placements(node.puzzle_state.placements)) for node in opened
        ]
        self._solver = solver

    def pop_open(self) -> tuple[SolverNode, list[Placement]] | tuple[None, None]:
        self._opened.sort(key=_get_num_placements, reverse=True)
        if not self._opened:
            return None, None
        return self._opened.pop()

    async def add_node_async(self, parent: Node, placement: Placement):
        session = self._shell.session
        state_id = await self._shell.upsert_board(parent.board, placement)
        try:
            async with session.begin_nested():
                session.add(
                    node := SolverNode(
                        solver_id=self._solver.id, puzzle_state_id=state_id, num_placements=len(parent.board.placements) + 1
                    )
                )
            self._opened.append((node, [*parent.board.placements, placement]))
            return node.status, False
        except IntegrityError:
            query = select(SolverNode).where(
                SolverNode.solver_id == self._solver.id, SolverNode.puzzle_state_id == state_id
            )
            node = (await session.execute(query)).scalar_one()
            return node.status, True


class SolverShell:
    @staticmethod
    async def load_node(session: AsyncSession, node_id: int) -> SolverNode:
        query = (
            select(SolverNode)
            .where(SolverNode.id == node_id)
            .options(joinedload(SolverNode.solver), joinedload(SolverNode.puzzle_state))
        )
        node: SolverNode = (await session.execute(query)).scalar_one()
        return node

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
        if not solver or solver.status != SolverStatus.SOLVED:
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
        state_id = await self.puzzle.upsert_board(await self.puzzle.load())
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
                logger.exception(f'An error occured during solve for {self.title}')
                error = str(ex)

            solver.finished_at = datetime.datetime.now(tz=datetime.UTC)
            solver.error = error
            solver.status = (
                SolverStatus.ERROR if error else SolverStatus.SOLVED if solutions else SolverStatus.NO_SOLUTIONS
            )
            await self.session.commit()

            logger.info(f'Finished background solve for {self.title} after {solver.iterations} iterations')
        except:
            await self.session.rollback()
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
            current_node, placements = orchestrator.pop_open()
            if not current_node or cancel_event.is_set():
                break
            board = orchestrator.board.copy(reset=False)
            for placement in placements:
                board.place(placement)
            node = Node(board)
            await node.expand_async(orchestrator, orchestrator)
            current_node.status = node.status
            if node.status == 'won':
                new_solutions.append(current_node)
            solver.iterations += 1
            await self.session.commit()
    
        return new_solutions, current_node is None
