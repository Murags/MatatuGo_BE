import os
import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATA_DIR.exists():
    raise FileNotFoundError(f"DATA_DIR not found: {DATA_DIR.resolve()}")

engine = create_engine(DATABASE_URL)

# --- Map dataset files to database tables ---
FILES_TO_TABLES = {
    "routes.txt": "routes",
    "stops.txt": "stages",
    "stop_times.txt": "stop_times",
    "shapes.txt": "shapes",
}


def load_txt_to_db(file_path: Path, table_name: str, replace: bool = False):
    """Load a text file into a PostgreSQL table, trimming extra columns safely."""
    print(f"\n Processing {file_path.name} → {table_name}")

    if not file_path.exists():
        print(f"Skipping: {file_path} not found")
        return

    df = pd.read_csv(file_path)
    print(f" → {len(df)} rows read")

    # --- Match DataFrame columns with DB table columns ---
    with engine.connect() as conn:
        table_cols = pd.read_sql(
            f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
            """,
            conn
        )["column_name"].tolist()

    # Drop any columns not in the DB table
    missing_cols = [c for c in df.columns if c not in table_cols]
    if missing_cols:
        print(f"Ignoring extra columns not in DB: {missing_cols}")
        df = df[[c for c in df.columns if c in table_cols]]

    # --- Load data into the database ---
    with engine.begin() as conn:
        if replace:
            print("Replacing table (DROP + CREATE)")
            df.to_sql(table_name, con=conn, if_exists="replace", index=False)
        else:
            print("Truncating and inserting new rows")
            conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))
            df.to_sql(table_name, con=conn, if_exists="append", index=False)

    print(f"Loaded {len(df)} rows into '{table_name}'")


def main():
    print(f"Starting data load from: {DATA_DIR.resolve()}")
    replace_mode = "--replace" in sys.argv

    for file_name, table in FILES_TO_TABLES.items():
        file_path = DATA_DIR / file_name
        try:
            load_txt_to_db(file_path, table, replace=replace_mode)
        except Exception as e:
            print(f"Error loading {file_name}: {e}")

    print("\nData load complete!")


if __name__ == "__main__":
    main()
