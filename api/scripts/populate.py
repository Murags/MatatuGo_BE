import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found")

engine = create_engine(DATABASE_URL)

# --- Test Data ---
fare_definitions_data = [
    {"fare_id": "F001", "price": 30.0, "currency_type": "KES", "payment_method": 0, "transfers": 0, "transfer_duration": None},
    {"fare_id": "F002", "price": 40.0, "currency_type": "KES", "payment_method": 0, "transfers": 0, "transfer_duration": None},
    {"fare_id": "F003", "price": 50.0, "currency_type": "KES", "payment_method": 0, "transfers": 1, "transfer_duration": 1800},
    {"fare_id": "F004", "price": 25.0, "currency_type": "KES", "payment_method": 0, "transfers": 0, "transfer_duration": None},
    {"fare_id": "F005", "price": 35.0, "currency_type": "KES", "payment_method": 0, "transfers": 1, "transfer_duration": 1200,},
]

fare_rules_data = [
    {"fare_id": "F001", "route_id": "10000107D11", "origin_id": "0100AAA", "destination_id": "0100AAB"},
    {"fare_id": "F002", "route_id": "10000116011", "origin_id": "0100AAE", "destination_id": "0100ACP"},
    {"fare_id": "F003", "route_id": "10100011A11", "origin_id": "0100AEI", "destination_id": "0100AEL"},
    {"fare_id": "F004", "route_id": "10200010811", "origin_id": "0100AKA", "destination_id": "0100AL2"},
    {"fare_id": "F005", "route_id": "10300011F11", "origin_id": "0100AMR", "destination_id": "0100AEL"},
]

transfers_data = [
    {"from_stop_id": "0100AAA", "to_stop_id": "0100AAE", "transfer_type": 0, "min_transfer_time": 120},
    {"from_stop_id": "0100AAE", "to_stop_id": "0100ACP", "transfer_type": 0, "min_transfer_time": 180},
    {"from_stop_id": "0100ACP", "to_stop_id": "0100AEI", "transfer_type": 0, "min_transfer_time": 240},
    {"from_stop_id": "0100AEI", "to_stop_id": "0100AEL", "transfer_type": 0, "min_transfer_time": 300},
    {"from_stop_id": "0100AEL", "to_stop_id": "0100AAA", "transfer_type": 1, "min_transfer_time": 600}
]


def populate_table(table_name: str, data: list[dict]):
    if not data:
        print(f"Skipping {table_name}: no data provided")
        return

    print(f"\nPopulating {table_name} with {len(data)} records")

    columns = ", ".join(data[0].keys())
    values = ", ".join([f":{key}" for key in data[0].keys()])
    query = text(f"INSERT INTO {table_name} ({columns}) VALUES ({values})")

    with engine.begin() as conn:
        # Clear existing records to avoid duplication
        conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE"))
        conn.execute(query, data)

    print(f"{table_name} Populated successfully")


def main():
    print("Starting manual data population\n")

    populate_table("fare_definitions", fare_definitions_data)
    populate_table("fare_rules", fare_rules_data)
    populate_table("transfers", transfers_data)

    print("\nData population complete")


if __name__ == "__main__":
    main()
