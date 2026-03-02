import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Thread

import psutil
from pydantic import BaseModel

from pips.app import models
from pips.data.boardfromstr import read_board_from_string
from pips.model import Board

logger = logging.getLogger('pips.solve.shell')


PLACEMENT = re.compile(
    r'^  (?P<left>\d)(?P<right>\d) at \((?P<x>\d+), (?P<y>\d+)\) facing (?P<dir>north|south|east|west)'
)


class SolverJobModel(BaseModel):
    pid: int
    puzzle_name: str
    memory_usage_mb: float
    start_time: datetime
    output: list[str]


@dataclass
class SolverJob:
    shell: Shell
    model: SolverJobModel

    @property
    def file(self):
        return self.shell._data_file(self.model.puzzle_name, 'solver')

    def save(self):
        with open(self.file, 'w') as fp:
            fp.write(self.model.model_dump_json(indent=2))

    @staticmethod
    def start(shell: Shell, puzzle_name: str):
        solver_job = SolverJob(
            shell,
            SolverJobModel(
                pid=-1,
                puzzle_name=puzzle_name,
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
            ['python', '-u', '-m', 'pips.cli.solveproc', self.shell.get_puzzle_file(self.model.puzzle_name)],
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
        with open(self.shell._data_file(self.model.puzzle_name, 'result'), 'w') as fp:
            fp.write(result.model_dump_json(indent=2))

        logger.info(f'Removing record of {self}')
        os.unlink(self.file)


class SolverResultModel(BaseModel):
    puzzle_name: str
    peak_memory_usage_mb: float
    time_to_solve: timedelta
    completion_time: datetime
    error: str | None
    solutions: list[list[models.PlacementModel]]


class Shell:
    def __init__(self, samples_dir: str, data_dir: str, exclude: set[str]):
        self.samples_dir = samples_dir
        self.data_dir = data_dir
        self.exclude = exclude

    # def get_file(self, puzzle_name: str, extension: str):
    #     return os.path.join(self.samples_dir, f'{puzzle_name}.{extension}')

    def get_boards(self) -> dict[str, Board]:
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
                    boards[name] = read_board_from_string(fp.read())
            except ValueError:
                logger.exception(f'Failed to load puzzle {puzzle_file}')
        return boards

    def get_puzzle_file(self, puzzle_name: str) -> str:
        return os.path.join(self.samples_dir, f'{puzzle_name}.txt')

    def get_board(self, puzzle_name: str) -> Board:
        with open(self.get_puzzle_file(puzzle_name)) as fp:
            read_board_from_string(fp.read())

    def _data_file(self, puzzle_name: str, name: str):
        return os.path.join(self.data_dir, puzzle_name, name)

    def get_solver_job(self, puzzle_name: str) -> SolverJobModel | None:
        path = self._data_file(puzzle_name, 'solver')
        try:
            if os.path.exists(path):
                with open(path) as fp:
                    job = SolverJobModel.model_validate_json(fp.read())
                    return job if psutil.pid_exists(job.pid) else None
        except Exception:
            logger.exception(f'Unable to load solver job for {path}')
        return None

    def get_solver_result(self, puzzle_name: str) -> SolverResultModel | None:
        path = self._data_file(puzzle_name, 'result')
        try:
            if os.path.exists(path):
                with open(path) as fp:
                    return SolverResultModel.model_validate_json(fp.read())
        except Exception:
            logger.exception(f'Unable to load solver result for {path}')
        return None

    # def get_solvers(self) -> iter[SolverJobModel]:
    #     for name, pid_file in self._list('.solver'):
    #         try:
    #             yield self.get_solver_job(name)
    #         except Exception:
    #             logger.exception(f'Could not load solver for name `{name}`, file `{pid_file}`')

    def launch_solver(self, puzzle_name):
        try:
            self.get_board(puzzle_name)
            return SolverJob.start(self, puzzle_name).model
        except Exception as ex:
            raise RuntimeError(f'Could not launch solver for {puzzle_name}') from ex

    # def refresh_all_solvers(self):
    #     pass
