import functools
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import typing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Thread

import psutil
from pydantic import BaseModel, Field

from pips.app import models
from pips.data.boardfromstr import read_board_from_string
from pips.model import Board, BoardStatus, Domino, Location, Placement, Position

from .node import Node
from .solver import Solver

logger = logging.getLogger('pips.solve.shell')


PLACEMENT = re.compile(
    r'^  (?P<left>\d)(?P<right>\d) at \((?P<x>\d+), (?P<y>\d+)\) facing (?P<dir>north|south|east|west)'
)


class BackgroundSolveModel(BaseModel):
    thread: str
    iterations: int
    start_time: datetime
    output: list[str]
    is_running: typing.Annotated[bool, Field(default=False)]


class SolverJobModel(BaseModel):
    pid: int
    puzzle_name: str
    memory_usage_mb: float
    start_time: datetime
    output: list[str]


class SolverNodeModel(BaseModel):
    puzzle_name: str
    id: str
    status: str
    placements: list[models.PlacementModel]


@dataclass
class SolverJob:
    shell: 'PuzzleShell'
    model: SolverJobModel

    @property
    def file(self):
        return self.shell._data_file('solver')

    def save(self):
        with open(self.file, 'w') as fp:
            fp.write(self.model.model_dump_json(indent=2))

    @staticmethod
    def start(shell: 'PuzzleShell'):
        solver_job = SolverJob(
            shell,
            SolverJobModel(
                pid=-1,
                puzzle_name=shell._puzzle_name,
                memory_usage_mb=0,
                start_time=datetime.now(tz=UTC),
                output=[],
            ),
        )
        os.makedirs(os.path.dirname(solver_job.file), exist_ok=True)
        # mutex
        with open(solver_job.file, 'x'):
            pass
        solver_job.save()

        Thread(target=solver_job.run).start()
        logger.info(f'Started solver thread for {solver_job}')
        return solver_job

    def __str__(self):
        return f'solver job for {self.model.puzzle_name} pid {self.model.pid}'

    @staticmethod
    def find_orientation(name: str):
        for orientation in models.Orientation:
            if orientation.value.name == name:
                return orientation

    @staticmethod
    def parse_solutions(output: list[str]) -> list[list[models.PlacementModel]]:
        solutions, solution = [], None
        for chunk in output:
            for line in chunk.split('\n'):
                if line.startswith('Solution '):
                    solutions.append(solution := [])
                elif solution is not None and line.startswith('  '):
                    match = PLACEMENT.match(line)
                    if not match:
                        raise ValueError(f'Unmatching line in solution: {line}')
                    left, right, x, y = (int(match.group(name)) for name in ('left', 'right', 'x', 'y'))
                    solution.append(
                        models.PlacementModel(
                            domino=models.Domino(left, right),
                            loc=models.Location(x, y),
                            dir=match.group('dir'),
                        )
                    )
        return solutions

    def run(self):
        popen = subprocess.Popen(
            ['python', '-u', '-m', 'pips.cli.solveproc', self.shell.board_file],
            text=True,
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        self.model.pid = popen.pid
        process = psutil.Process(self.model.pid)
        memory_limit_mb = 2**13  # 8 GiB
        # process.rlimit(psutil.RLIMIT_AS, (2 ** 33,) * 2)  # 8 GiB soft & hard
        self.model.memory_usage_mb = process.memory_info().rss / (2**20)
        self.save()

        logger.info(f'Launched process for {self}')

        output = []

        def read_output():
            logger.info(f'Beginning read output for {self}')
            for line in popen.stdout:
                output.append(line)
            logger.info(f'Finished reading output for {self}')

        thread = Thread(target=read_output)
        thread.start()

        peak_memory_usage = self.model.memory_usage_mb
        termination_reason = None
        logger.info(f'Beginning waiting for {self}')
        while True:
            time.sleep(2)
            if popen.poll() is not None:
                break
            self.model.memory_usage_mb = memory_usage = process.memory_info().rss / (2**20)
            # print(f'memory_info {process.memory_info()}')
            if memory_usage > peak_memory_usage:
                peak_memory_usage = memory_usage
            self.model.output = list(output)
            self.save()

            if memory_usage > memory_limit_mb:
                logger.info(f'Termainting solver job {self} for exceeding memory limit: {memory_usage}')
                termination_reason = 'Exceeded memory limit'
                popen.terminate()

        logger.info(f'Finished waiting for {self}')

        thread.join()

        logger.info(f'Last 5 outputs of {self}: {output[-5:]}')

        completion_time = datetime.now(UTC)
        return_code = popen.returncode
        if not return_code and termination_reason:
            return_code = -99
        result = SolverResultModel(
            puzzle_name=self.model.puzzle_name,
            peak_memory_usage_mb=peak_memory_usage,
            iterations=0,
            time_to_solve=completion_time - self.model.start_time,
            completion_time=completion_time,
            error=(
                termination_reason
                if termination_reason
                else f'Solver exited with status {return_code}'
                if return_code
                else None
            ),
            solutions=self.parse_solutions(output),
        )
        with open(self.shell._data_file('result'), 'w') as fp:
            fp.write(result.model_dump_json(indent=2))
        self.shell.set_result_status('error' if result.error else 'solved' if result.solutions else 'no_solutions')
        logger.info(f'Removing record of {self}')
        os.unlink(self.file)


class SolverResultModel(BaseModel):
    puzzle_name: str
    peak_memory_usage_mb: float
    iterations: int
    time_to_solve: timedelta
    completion_time: datetime
    error: str | None
    solutions: list[list[models.PlacementModel]]


ResultStatus = typing.Literal['not_run', 'no_solutions', 'error', 'solved']

FileSuffix: dict[str, ResultStatus] = {'nos': 'no_solutions', 'err': 'error', 'sol': 'solved'}


class Shell:
    def __init__(self, samples_dir: str, data_dir: str, exclude: set[str]):
        self.samples_dir = samples_dir
        self.data_dir = data_dir
        self.exclude = exclude

    def puzzle(self, puzzle_name: str) -> PuzzleShell:
        return PuzzleShell(self, puzzle_name)

    def get_boards(self) -> dict[str, tuple[Board, ResultStatus]]:
        boards = {}
        puzzle_files = []
        for name in os.listdir(self.samples_dir):
            if name.endswith('.txt'):
                puzzle_files.append((name[:-4], os.path.join(self.samples_dir, name)))

        for name, puzzle_file in sorted(puzzle_files):
            if name in self.exclude:
                continue
            try:
                with open(puzzle_file) as fp:
                    board = read_board_from_string(fp.read())
                status: ResultStatus = 'not_run'
                for suffix, test_status in FileSuffix.items():
                    if os.path.exists(self._data_file(name, f'result.{suffix}')):
                        status = test_status
                boards[name] = (board, status)
            except ValueError:
                logger.exception(f'Failed to load puzzle {puzzle_file}')
        return boards

    def get_board(self, puzzle_name: str) -> Board:
        return PuzzleShell(self, puzzle_name).get_board()

    def _data_file(self, *names: str):
        return os.path.join(self.data_dir, *names)


class ShellSolver(Solver):
    def __init__(self, shell: 'PuzzleShell'):
        super().__init__(shell.get_board())
        self._shell = shell
        self._opened: list[str] = shell.get_solver_node_ids('null')

    def pop_open(self) -> str | None:
        self._opened.sort(key=len, reverse=True)
        if not self._opened:
            return None
        return self._opened.pop()

    def add_node(self, parent, placement):
        new_state = [*parent.board.placements, placement]
        node_id = '/'.join(f'{placement.brief}' for placement in new_state)
        node = self._shell.get_solver_node(node_id)
        if node:
            return node.status, True

        data_file = functools.partial(self._shell._data_file, 'nodes', node_id)
        os.makedirs(data_file(), exist_ok=True)

        node_model = SolverNodeModel(
            puzzle_name=self._shell._puzzle_name,
            id=node_id,
            status='null',
            placements=[
                models.PlacementModel(domino=placement.domino, loc=placement.pos.loc, dir=placement.pos.dir.value.name)
                for placement in new_state
            ],
        )

        with open(data_file('state'), 'w') as fp:
            fp.write(node_model.model_dump_json(indent=2))
        with open(data_file('status=null'), 'w') as fp:
            pass
        self._opened.append(node_id)
        return 'null', False


class PuzzleShell:
    def __init__(self, shell: Shell, puzzle_name: str):
        self._shell = shell
        self._puzzle_name = puzzle_name

    @property
    def board_file(self) -> str:
        return os.path.join(self._shell.samples_dir, f'{self._puzzle_name}.txt')

    def _data_file(self, *names: tuple[str, ...]):
        return self._shell._data_file(self._puzzle_name, *names)

    def set_result_status(self, status: ResultStatus):
        for suffix, test_status in FileSuffix.items():
            file_path = self._data_file(f'result.{suffix}')
            exists = os.path.exists(file_path)
            if exists and status != test_status:
                os.unlink(file_path)
            elif not exists and status == test_status:
                with open(file_path, 'w'):
                    pass

    def get_board(self) -> Board:
        with open(self.board_file) as fp:
            return read_board_from_string(fp.read())

    def get_solver_job(self) -> BackgroundSolveModel | None:
        path = self._data_file('nodes', 'bgsolve')
        try:
            if os.path.exists(path):
                with open(path) as fp:
                    return BackgroundSolveModel.model_validate_json(fp.read())
        except Exception:
            logger.exception(f'Unable to load solver job for {path}')
        return None

    def get_solver_result(self) -> SolverResultModel | None:
        path = self._data_file('result')
        try:
            if os.path.exists(path):
                with open(path) as fp:
                    return SolverResultModel.model_validate_json(fp.read())
        except Exception:
            logger.exception(f'Unable to load solver result for {path}')
        return None

    def has_any_nodes(self) -> bool:
        for _, _, filenames in os.walk(self._data_file('nodes/')):
            if 'state' in filenames:
                return True
        return False

    def get_solver_node_ids(self, status: str | None = None) -> list[str]:
        nodes = self._data_file('nodes/')
        if not os.path.exists(nodes):
            return []
        status_filename = f'status={status}' if status else None
        return [
            dirpath[len(nodes) :]
            for dirpath, dirnames, filenames in os.walk(nodes)
            if 'state' in filenames and (not status_filename or status_filename in filenames)
        ]

    def get_solver_node(self, node_id: str) -> SolverNodeModel | None:
        node_path = self._data_file('nodes', node_id, 'state')
        if not os.path.exists(node_path):
            return None
        with open(node_path) as fp:
            return SolverNodeModel.model_validate_json(fp.read())

    def init_background_solve(self) -> BackgroundSolveModel:
        lock_file = self._data_file('nodes', 'bgsolve.lock')
        os.makedirs(os.path.dirname(lock_file), exist_ok=True)
        with open(lock_file, 'x'):
            pass

        job = self._load_bg_job() or BackgroundSolveModel(
            thread=threading.current_thread().name,
            iterations=0,
            start_time=datetime.now(tz=UTC),
            is_running=True,
            output=[],
        )

        job.is_running = True
        self._save_bg_job(job)
        return job

    def _load_bg_job(self) -> BackgroundSolveModel | None:
        job_path = self._data_file('nodes', 'bgsolve')
        if not os.path.exists(job_path):
            return None

        with open(job_path) as fp:
            return BackgroundSolveModel.model_validate_json(fp.read())

    def _save_bg_job(self, job: BackgroundSolveModel):
        job_path = self._data_file('nodes', 'bgsolve')
        temp_path = f'{job_path}.tmp'
        os.makedirs(os.path.dirname(job_path), exist_ok=True)
        with open(temp_path, 'w') as fp:
            fp.write(job.model_dump_json(indent=2))
        os.replace(temp_path, job_path)

    def background_solve(self, shutdown_event: threading.Event):
        try:
            self._background_solve(shutdown_event)
        finally:
            os.unlink(self._data_file('nodes', 'bgsolve.lock'))
            job = self._load_bg_job()
            if job:
                job.is_running = False
                self._save_bg_job(job)

    def _background_solve(self, shutdown_event: threading.Event):
        job = self._load_bg_job()
        job.thread = threading.current_thread().name
        solutions = [
            node.placements for node in [self.get_solver_node(node_id) for node_id in (self.get_solver_node_ids('won'))]
        ]
        logger.info(
            f'Starting background solve for {self._puzzle_name} thread {job.thread}, {len(solutions)} solutions so far'
        )

        try:
            while True:
                if shutdown_event.is_set():
                    return
                more_solutions, finished = self.run_steps(job, 100)
                solutions.extend(more_solutions)
                if finished:
                    break
            error = None
        except Exception as ex:
            error = str(ex)

        completion_time = datetime.now(tz=UTC)
        result = SolverResultModel(
            puzzle_name=self._puzzle_name,
            peak_memory_usage_mb=0,
            iterations=job.iterations,
            time_to_solve=completion_time - job.start_time,
            completion_time=completion_time,
            error=error,
            solutions=solutions,
        )
        with open(self._data_file('result'), 'w') as fp:
            fp.write(result.model_dump_json(indent=2))
        self.set_result_status('error' if error else 'solved' if solutions else 'no_solutions')
        os.unlink(self._data_file('nodes', 'bgsolve'))
        logger.info(f'Finished background solve for {self._puzzle_name} after {job.iterations} iterations')

    def reset_background_solver(self):
        shutil.rmtree(self._data_file('nodes'))

    def launch_solver(self):
        try:
            self.get_board()
            return SolverJob.start(self._shell, self._puzzle_name).model
        except Exception as ex:
            raise RuntimeError(f'Could not launch solver for {self._puzzle_name}') from ex

    def _find_next_open_node(self) -> SolverNodeModel | None:
        open_nodes = self.get_solver_node_ids('null')
        if len(open_nodes) == 0:
            return None
        return self.get_solver_node(open_nodes[0])

    def _set_node_status(self, node: SolverNodeModel, status: BoardStatus):
        # update the status of the start node
        data_file = functools.partial(self._data_file, 'nodes', node.id)
        old_status = data_file(f'status={node.status}')
        new_status = data_file(f'status={status}')
        state_file = data_file('state')
        try:
            os.unlink(old_status)
        except IOError:
            logger.error(f'Could not remove old status file: {old_status}')
        node.status = status
        with open(state_file, 'w') as fp:
            fp.write(node.model_dump_json(indent=2))
        with open(new_status, 'w') as fp:
            pass
        logger.debug(f'Upated start node {node.id} with status={node.status}')

    def run_steps(self, job: BackgroundSolveModel, count: int) -> bool:
        solver = ShellSolver(self)
        current_node_id = solver.pop_open()
        save_node = True
        if not current_node_id:
            if self.has_any_nodes():
                return [], True
            current_node = SolverNodeModel(puzzle_name=self._puzzle_name, id='', status='incomplete', placements=[])
            save_node = False
        else:
            current_node = self.get_solver_node(current_node_id)

        # board = self.get_board()
        # start_node = self._find_next_open_node()
        # save_start_node = True
        # if not start_node:
        #     if self.has_any_nodes():
        #         return None
        #     start_node = SolverNodeModel(puzzle_name=self._puzzle_name, id='', status='incomplete', placements=[])
        #     save_start_node = False
        # for placement in start_node.placements:
        #     board.place(Placement(Domino(*placement.domino), Position(Location(*placement.loc), placement.dir)))

        # solver = ShellSolver(self)
        new_solutions = []
        for _ in range(count):
            board = solver.board.copy(reset=False)
            for placement in current_node.placements:
                board.place(Placement(Domino(*placement.domino), Position(Location(*placement.loc), placement.dir)))
            node = Node(board)
            node.expand(solver, solver)
            if save_node:
                self._set_node_status(current_node, node.status)
            if node.status == 'won':
                new_solutions.append(current_node.placements)
            job.iterations += 1
            self._save_bg_job(job)
            if not (current_node_id := solver.pop_open()):
                break
            current_node = self.get_solver_node(current_node_id)
            save_node = True

        return new_solutions, current_node_id is None
