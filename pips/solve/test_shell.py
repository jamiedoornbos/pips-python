from pips.solve.shell import SolverJob, SolverResultModel


def test_parse_solutions():
    solutions = SolverJob.parse_solutions(
        [
            'Loaded board: samples/2026-02-18-medium.txt\nCompleted depth 0; 46 open nodes\n'
            'Completed depth 1; 567 open nodes\nCompleted depth 2; 2059 open nodes\n'
            'Completed depth 3; 1467 open nodes\nCompleted depth 4; 152 open nodes\n'
            'Completed depth 5; 4 open nodes\nSolution #1\n  01 at (4, 3) facing west\n'
            '  15 at (2, 3) facing north\n  22 at (0, 0) facing east\n  43 at (2, 0) facing south\n'
            '  55 at (3, 0) facing east\n  61 at (0, 3) facing east\nSolution #2\n  01 at (4, 3) facing west\n'
            '  15 at (2, 3) facing north\n  22 at (0, 0) facing east\n  43 at (2, 0) facing south\n'
            '  55 at (4, 0) facing west\n  61 at (0, 3) facing east\nSolution #3\n  01 at (4, 3) facing west\n'
            '  15 at (2, 3) facing north\n  22 at (1, 0) facing west\n  43 at (2, 0) facing south\n'
            '  55 at (3, 0) facing east\n  61 at (0, 3) facing east\nSolution #4\n  01 at (4, 3) facing west\n'
            '  15 at (2, 3) facing north\n  22 at (1, 0) facing west\n  43 at (2, 0) facing south\n'
            '  55 at (4, 0) facing west\n  61 at (0, 3) facing east\n'
        ]
    )
    assert len(solutions) == 4


def test_solver_result_deserialize():
    serialized = """{
  "puzzle_name": "2026-02-18-medium",
  "peak_memory_usage_mb": 400449.265625,
  "time_to_solve": "PT5.011884S",
  "completion_time": "2026-02-27T16:49:17.980208Z",
  "error": null,
  "solutions": [
    [
      {
        "domino": [
          0,
          1
        ],
        "loc": [
          4,
          3
        ],
        "dir": "west"
      },
      {
        "domino": [
          1,
          5
        ],
        "loc": [
          2,
          3
        ],
        "dir": "north"
      },
      {
        "domino": [
          2,
          2
        ],
        "loc": [
          0,
          0
        ],
        "dir": "east"
      },
      {
        "domino": [
          4,
          3
        ],
        "loc": [
          2,
          0
        ],
        "dir": "south"
      },
      {
        "domino": [
          5,
          5
        ],
        "loc": [
          3,
          0
        ],
        "dir": "east"
      },
      {
        "domino": [
          6,
          1
        ],
        "loc": [
          0,
          3
        ],
        "dir": "east"
      }
    ],
    [
      {
        "domino": [
          0,
          1
        ],
        "loc": [
          4,
          3
        ],
        "dir": "west"
      },
      {
        "domino": [
          1,
          5
        ],
        "loc": [
          2,
          3
        ],
        "dir": "north"
      },
      {
        "domino": [
          2,
          2
        ],
        "loc": [
          0,
          0
        ],
        "dir": "east"
      },
      {
        "domino": [
          4,
          3
        ],
        "loc": [
          2,
          0
        ],
        "dir": "south"
      },
      {
        "domino": [
          5,
          5
        ],
        "loc": [
          4,
          0
        ],
        "dir": "west"
      },
      {
        "domino": [
          6,
          1
        ],
        "loc": [
          0,
          3
        ],
        "dir": "east"
      }
    ],
    [
      {
        "domino": [
          0,
          1
        ],
        "loc": [
          4,
          3
        ],
        "dir": "west"
      },
      {
        "domino": [
          1,
          5
        ],
        "loc": [
          2,
          3
        ],
        "dir": "north"
      },
      {
        "domino": [
          2,
          2
        ],
        "loc": [
          1,
          0
        ],
        "dir": "west"
      },
      {
        "domino": [
          4,
          3
        ],
        "loc": [
          2,
          0
        ],
        "dir": "south"
      },
      {
        "domino": [
          5,
          5
        ],
        "loc": [
          3,
          0
        ],
        "dir": "east"
      },
      {
        "domino": [
          6,
          1
        ],
        "loc": [
          0,
          3
        ],
        "dir": "east"
      }
    ],
    [
      {
        "domino": [
          0,
          1
        ],
        "loc": [
          4,
          3
        ],
        "dir": "west"
      },
      {
        "domino": [
          1,
          5
        ],
        "loc": [
          2,
          3
        ],
        "dir": "north"
      },
      {
        "domino": [
          2,
          2
        ],
        "loc": [
          1,
          0
        ],
        "dir": "west"
      },
      {
        "domino": [
          4,
          3
        ],
        "loc": [
          2,
          0
        ],
        "dir": "south"
      },
      {
        "domino": [
          5,
          5
        ],
        "loc": [
          4,
          0
        ],
        "dir": "west"
      },
      {
        "domino": [
          6,
          1
        ],
        "loc": [
          0,
          3
        ],
        "dir": "east"
      }
    ]
  ]
}"""
    SolverResultModel.model_validate_json(serialized)
