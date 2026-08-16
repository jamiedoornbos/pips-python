import asyncio
import datetime
import logging
import typing

import sqlalchemy
import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from pips.app.models import PlacementModel
from pips.db.model.puzzle_state import PuzzleState
from pips.db.model.solver import Solver, SolverStatus
from pips.db.model.solver_node import SolverNode, SolverNodeStatus
from pips.db.puzzles import CatalogShell, PuzzleVersionShell, bytes_to_placements, placements_to_bytes
from pips.db.session import async_session
from pips.model.board import Board
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


def _get_num_placements(entry: tuple[SolverNode, bytes]):
    return entry[0].num_placements


class DatabaseNodeOrchestrator(CoreSolver):
    def __init__(
        self,
        board: Board,
        solver: Solver,
        all_nodes: typing.Sequence[SolverNode],
        all_states: typing.Sequence[PuzzleState],
    ):
        super().__init__(board)
        self._solver = solver
        self._opened: list[tuple[SolverNode, bytes]] = [
            (node, node.puzzle_state.placements) for node in all_nodes if node.status == SolverNodeStatus.UNVISITED
        ]
        self._new: list[SolverNode] = []

        nodes = {node.puzzle_state.placements: node for node in all_nodes}
        self._cache: dict[bytes, tuple[SolverNode | None, PuzzleState | int]] = {
            state.placements: (nodes.get(state.placements), state.id) for state in all_states
        }

    def pop_open(self) -> tuple[SolverNode | None, bytes | None]:
        self._opened.sort(key=_get_num_placements, reverse=True)
        if not self._opened:
            return None, None
        return self._opened.pop()

    def add_node(self, parent: Node, placement: Placement):
        if cached := self._cache.get(placements_bytes := placements_to_bytes([*parent.board.placements, placement])):
            child, state_or_id = cached
            if child:
                return True

            kwargs = {'puzzle_state' if isinstance(cached, PuzzleState) else 'puzzle_state_id': state_or_id}
        else:
            kwargs = {
                'puzzle_state': (
                    state_or_id := PuzzleState(
                        puzzle=self._solver.puzzle,
                        placements=placements_bytes,
                    )
                )
            }

        self._new.append(
            child := SolverNode(num_placements=len(parent.board.placements) + 1, solver=self._solver, **kwargs)
        )
        self._cache[placements_bytes] = (child, state_or_id)
        self._opened.append((child, placements_bytes))
        return False

    def flush(self) -> list[SolverNode]:
        nodes = self._new
        self._new = []
        return nodes


class RunStepsResult(typing.NamedTuple):
    iterations: int
    solutions: int
    completed: bool


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

        assert solver.finished_at is not None  # guaranteed once status is SOLVED

        solutions = []
        for solution in await self.get_solutions():
            solutions.append(
                [
                    PlacementModel(domino=placement.domino, loc=placement.pos.loc, dir=placement.pos.dir)
                    for placement in bytes_to_placements(solution.puzzle_state.placements)
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
                    select(Solver)
                    .where(Solver.puzzle_title == title, Solver.puzzle_version == version)
                    .options(selectinload(Solver.puzzle))
                )
            )
            .scalars()
            .one()
        )

    async def reset_solver(self) -> None:
        solver = await self.load()
        if solver:
            await self.session.delete(solver)

    async def init_solver(self) -> BackgroundSolveModel:
        title = self.puzzle.title
        version = self.puzzle.version
        try:
            self.session.add_all(
                [
                    solver := Solver(puzzle_title=title, puzzle_version=version),
                    SolverNode(
                        num_placements=0,
                        solver=solver,
                        puzzle_state=await self.puzzle.upsert_state(),
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

            if solver.status not in (SolverStatus.NOT_RUN, SolverStatus.ERROR):
                raise RuntimeError(f'Solver already completed for {self.title}')

            # TODO: use FOR UPDATE and prevent race condition
            solver.lock = True
            await self.session.commit()

            all_nodes = await self.get_nodes()
            solutions = sum(1 for node in all_nodes if node.status == SolverNodeStatus.WON)
            iterations = solver.iterations
            logger.info(
                f'Starting solve for {self.title} version {self.version} - {solutions=} and {iterations=} '
                f'all_nodes={len(all_nodes)}'
            )

            finished = False
            board = await self.puzzle.load()
            assert board
            orchestrator = DatabaseNodeOrchestrator(board, solver, all_nodes, await self.puzzle.get_states())
            del all_nodes

            flush_task: asyncio.Future | None = None

            async def flush(final: bool = False):
                nonlocal flush_task
                if flush_task and not flush_task.done():
                    logger.warning(f'Awaiting last save ({self.title} version {self.version})')
                    await flush_task
                self.session.add_all(orchestrator.flush())
                flush_task = asyncio.create_task(self.session.commit())
                if final:
                    await flush_task

            try:
                while True:
                    if cancel_event.is_set():
                        break
                    iterations, new_solutions, finished = await self.run_steps(orchestrator, cancel_event, 1000)
                    solver.iterations += iterations
                    solutions += new_solutions
                    await flush()
                    if finished:
                        break
                error = None
            except Exception as ex:
                logger.exception(f'An error occured during solve for {self.title}')
                error = str(ex)

            solver.finished_at = datetime.datetime.now(tz=datetime.UTC) if finished else None
            solver.error = error
            solver.status = (
                SolverStatus.ERROR
                if error
                else SolverStatus.NOT_RUN
                if not finished
                else SolverStatus.SOLVED
                if solutions
                else SolverStatus.NO_SOLUTIONS
            )
            await flush(final=True)

            logger.info(f'Finished background solve for {self.title} after {solver.iterations} iterations')
        except:
            await self.session.rollback()
            raise
        finally:
            await self.session.rollback()
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

    async def get_solutions(self) -> typing.Sequence[SolverNode]:
        return await self.get_nodes(SolverNodeStatus.WON)

    async def get_nodes(self, status: SolverNodeStatus | None = None) -> typing.Sequence[SolverNode]:
        query = self._my_nodes().options(joinedload(SolverNode.puzzle_state))
        if status:
            query = query.where(SolverNode.status == status)
        return (await self.session.execute(query)).scalars().all()

    async def run_steps(
        self, orchestrator: DatabaseNodeOrchestrator, cancel_event: asyncio.Event, count: int
    ) -> RunStepsResult:
        iterations, solutions = 0, 0

        for _ in range(count):
            current_node, placement_bytes = orchestrator.pop_open()
            if not (current_node and placement_bytes) or cancel_event.is_set():
                break
            board = orchestrator.board.copy(reset=False)
            for placement in bytes_to_placements(placement_bytes):
                board.place(placement)
            node = Node(board)
            node.expand(orchestrator, orchestrator)
            match node.status:
                case 'won':
                    current_node.status = SolverNodeStatus.WON
                    solutions += 1
                case 'lost':
                    current_node.status = SolverNodeStatus.LOST
                case 'incomplete':
                    current_node.status = SolverNodeStatus.INCOMPLETE
                case _:
                    assert False, f'Unexpected status {node.status}'
            iterations += 1

        return RunStepsResult(iterations, solutions, current_node is None)
