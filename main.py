"""TownshipOS entry point.

  python main.py                 launch the app (loads sample data only if the database is empty)
  python main.py --init-db       create tables and load sample data if the database is empty
  python main.py --reset-sample  DELETE all records and reload the synthetic sample data
"""
import argparse

from config import DB_PATH
from data.database import init_db
from data.seed import reset_and_seed, seed_if_empty


def main():
    parser = argparse.ArgumentParser(description="TownshipOS prototype")
    parser.add_argument("--init-db", action="store_true", help="create tables and seed if empty, then exit")
    parser.add_argument("--set-staff-pin", action="store_true",
                        help="set or change the staff PIN (prompts securely), then exit")
    parser.add_argument("--reset-sample", action="store_true",
                        help="delete ALL records and load the synthetic sample data, then exit")
    args = parser.parse_args()

    conn = init_db()
    print(f"Database: {DB_PATH.resolve()}")

    if args.set_staff_pin:
        import getpass
        from services import auth
        from services.errors import TownshipError
        pin = getpass.getpass("New staff PIN: ")
        if pin != getpass.getpass("Type it again: "):
            print("The PINs did not match. Nothing changed.")
            return
        try:
            auth.set_staff_pin(conn, pin)
            print("Staff PIN saved.")
        except TownshipError as exc:
            print(exc)
        return
    if args.reset_sample:
        reset_and_seed(conn)
        print("All records deleted and synthetic sample data loaded.")
        return
    if args.init_db:
        seeded = seed_if_empty(conn)
        print("Sample data loaded." if seeded else "Database already contains data; nothing changed.")
        return

    seed_if_empty(conn)
    import flet as ft
    from ui.app import TownshipApp
    ft.app(target=lambda page: TownshipApp(page, conn))


if __name__ == "__main__":
    main()
