import logging
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Thread

import psutil
from pydantic import BaseModel

from pips.app.models import PlacementModel
from pips.data.boardfromstr import read_board_from_string
from pips.model import Board

logger = logging.getLogger('pips.solve.shell')


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

    def get_file(self, extension: str):
        return self.shell.get_file(self.model.puzzle_name, extension)

    @property
    def file(self):
        return self.get_file('solver')

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
        # mutex
        with open(solver_job.file, 'x'):
            pass
        solver_job.save()

        Thread(target=solver_job.run).start()
        logger.info(f'Started solver thread for {solver_job}')
        return solver_job

    def __str__(self):
        return f'solver job for {self.model.puzzle_name} pid {self.model.pid}'

    def run(self):
        popen = subprocess.Popen(
            ['python', '-m', 'pips.cli.solve', '--quiet', self.get_file('txt')],
            text=True,
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        self.model.pid = popen.pid
        process = psutil.Process(self.model.pid)
        # process.rlimit(psutil.RLIMIT_AS, (2 ** 33,) * 2)  # 8 GiB soft & hard
        self.model.memory_usage_mb = process.memory_info().vms / (2**20)
        self.save()

        logger.info(f'Launched process for {self}')

        output = []

        def read_output():
            logger.info(f'Beginning read output for {self}')
            while True:
                stdout, _ = popen.communicate(timeout=5)
                if stdout:
                    output.append(stdout)
                if popen.poll() is not None:
                    break
            logger.info(f'Finished reading output for {self}')

        thread = Thread(target=read_output)
        thread.start()

        max_memory_usage = self.model.memory_usage_mb
        logger.info(f'Beginning waiting for {self}')
        while True:
            time.sleep(5)
            if popen.poll() is not None:
                break
            self.model.memory_usage_mb = process.memory_info().vms / (2**20)
            if self.model.memory_usage_mb > max_memory_usage:
                max_memory_usage = self.model.memory_usage_mb
            self.model.output = list(output)
            self.save()
        logger.info(f'Finished waiting for {self}')

        thread.join()

        logger.info(f'Last 5 outputs of {self}: {output[-5:]}')

        completion_time = datetime.now(UTC)
        return_code = popen.returncode
        result = SolverResultModel(
            puzzle_name=self.model.puzzle_name,
            max_memory_usage_mb=max_memory_usage,
            time_to_solve=completion_time - self.model.start_time,
            completion_time=completion_time,
            error=None if return_code == 0 else f'Solver exited with status {return_code}',
            solutions=[],
        )
        with open(self.get_file('result'), 'w') as fp:
            fp.write(result.model_dump_json(indent=2))

        logger.info(f'Removing record of {self}')
        os.unlink(self.file)


class SolverResultModel(BaseModel):
    puzzle_name: str
    max_memory_usage_mb: float
    time_to_solve: timedelta
    completion_time: datetime
    error: str | None
    solutions: list[list[PlacementModel]]


class Shell:
    def __init__(self, dir_: str, exclude: set[str]):
        self.dir = dir_
        self.exclude = exclude

    def _list(self, extension: str) -> iter[str]:
        for name in os.listdir(self.dir):
            if name.endswith(extension):
                yield name[: -len(extension)], os.path.join(self.dir, name)

    def get_file(self, puzzle_name: str, extension: str):
        return os.path.join(self.dir, f'{puzzle_name}.{extension}')

    def get_boards(self) -> dict[str, Board]:
        boards = {}
        for name, puzzle_file in sorted(self._list('.txt')):
            if name in self.exclude:
                continue
            try:
                with open(puzzle_file) as fp:
                    boards[name] = read_board_from_string(fp.read())
            except ValueError:
                logger.exception(f'Failed to load puzzle {puzzle_file}')
        return boards

    def get_solver_job(self, puzzle_name: str) -> SolverJobModel | None:
        path = self.get_file(puzzle_name, 'solver')
        try:
            if os.path.exists(path):
                with open(path) as fp:
                    job = SolverJobModel.model_validate_json(fp.read())
                    return job if psutil.pid_exists(job.pid) else None
        except Exception:
            logger.exception(f'Unable to load solver job for {path}')
        return None

    def get_solver_result(self, puzzle_name: str) -> SolverResultModel | None:
        path = self.get_file(puzzle_name, 'result')
        try:
            if os.path.exists(path):
                with open(path) as fp:
                    return SolverResultModel.model_validate_json(fp.read())
        except Exception:
            logger.exception(f'Unable to load solver result for {path}')
        return None

    def get_solvers(self) -> iter[SolverJobModel]:
        for name, pid_file in self._list('.solver'):
            try:
                yield self.get_solver_job(name)
            except Exception:
                logger.exception(f'Could not load solver for name `{name}`, file `{pid_file}`')

    def launch_solver(self, puzzle_name):
        try:
            with open(self.get_file(puzzle_name, 'txt')) as fp:
                read_board_from_string(fp.read())
            return SolverJob.start(self, puzzle_name).model
        except Exception as ex:
            raise RuntimeError(f'Could not launch solver for {puzzle_name}') from ex

    def refresh_all_solvers(self):
        pass
