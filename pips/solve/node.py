from pips.model import Board, BoardStatus


class Node:
    _board: Board
    _children: list["Node"]
    _messages: list[str]
    _status: BoardStatus | None = None

    def __init__(self, board: Board):
        self._board = board
        self._children = []
        self._messages = []
        self._status = None


"""
export default class SolverNode {
  _board: Board;
  _children: SolverNode[] = [];
  _messages: string[] = [];
  _status: BoardStatus | null = null;

"""
