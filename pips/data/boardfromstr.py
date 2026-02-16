import collections

from pips.model import Board, Constraint, ConstraintType, Domino, Location, LocationSet, PipCount


def _read_sections(lines: list[str]) -> dict[str, str]:
    sections = {}
    section = []
    for line in lines:
        line = line.strip()
        if line == "":
            pass
        elif line.startswith("# "):
            name = line[2:]
            sections[name] = section = []
        else:
            section.append(line)
    return sections


def _domino_from_string(domino: str) -> Domino:
    if len(domino) != 2:
        raise ValueError("Domino must have exactly 2 pip counts")

    pips: list[PipCount] = []
    for char in domino:
        value = ord(char) - ord("0")
        if value < 0 or value > 6:
            raise ValueError(f"Pip count `{char}` must be 0 to 6")
        pips.append(value)
    return Domino(*pips)


def read_board_from_string(serialized: str) -> Board:
    sections = _read_sections(serialized.split("\n"))

    # read background and constraint locations
    background: set[Location] = set()
    constraint_map: dict[str, set[Location]] = collections.defaultdict(set)
    y = 0
    for line in sections["Background"] or []:
        x = 0
        for char in line:
            if char == ".":
                pass
            else:
                location = Location(x, y)
                if char == "@":
                    pass
                else:
                    constraint_map[char].add(location)
                background.add(location)
            x += 1
        y += 1

    if not len(background):
        raise ValueError("Game board has no tiles")

    if not len(constraint_map):
        raise ValueError("Game board has no constraints")

    # read constraints
    constraints: list[Constraint] = []
    for line in sections["Constraints"] or []:
        name, operation_and_value = [token.strip() for token in line.split(":", 1)]
        if not operation_and_value:
            raise ValueError(f"Invalid constraint: {line}")
        tiles = constraint_map[name]
        del constraint_map[name]
        if not len(tiles):
            raise ValueError(f"Constraint {line} specifies non-existent constraint name `{name}`")
        operation_and_value = operation_and_value.split(" ", 1)
        type = ConstraintType.from_name(operation_and_value[0])
        if type.is_sum:
            if len(operation_and_value) < 2 or not operation_and_value[1]:
                raise ValueError(f"Constraint {line} must have a value")
            value = int(operation_and_value[1])
        else:
            if len(operation_and_value) > 1 and operation_and_value[1]:
                raise ValueError(f"Constraint {line} must not have a value")
            value = None
        constraints.append(Constraint(LocationSet(tiles), type, value))

    # check for missing constraints
    if constraint_map:
        raise ValueError(f"Constraints {', '.join(constraint_map.keys())} are not defined")

    # read dominoes
    dominoes: list[Domino] = []
    for line in sections["Dominoes"] or []:
        for pair in line.split(" "):
            dominoes.append(_domino_from_string(pair))

    if not dominoes:
        raise ValueError(f"No dominoes found")

    # check for sizing
    if len(dominoes) * 2 != len(background):
        raise ValueError(f"{len(dominoes)} dominoes won't fill game board with {len(background)} tiles")

    # check for duplicates
    if duplicates := [domino for domino, count in collections.Counter(dominoes).items() if count > 1]:
        raise ValueError(f"Domino(es) {', '.join(str(domino) for domino in duplicates)} are duplicated")

    return Board(LocationSet(background), constraints, dominoes)
