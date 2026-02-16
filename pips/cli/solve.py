import click

from pips.data.boardfromstr import read_board_from_string


@click.command()
@click.argument("filename")
def main(filename: str):
    with open(filename, encoding="utf8") as fp:
        board = read_board_from_string(fp.read())

    print(f"Loaded board: {board}")


if __name__ == "__main__":
    main()
