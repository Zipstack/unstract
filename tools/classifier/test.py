import csv
import json
import sys
from datetime import datetime


def parse_value(value):
    if value in ["None", ""]:
        return None
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%b %d, %Y").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def parse_float(value):
    try:
        return float(value.replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def parse_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def process_tsv(file_name):
    with open(file_name, newline="", encoding="utf-8") as tsvfile:
        reader = csv.reader(tsvfile, delimiter="\t")
        json_output = []
        for row_index, row in enumerate(reader):
            unit_num = parse_value(row[2])
            unit_type = parse_value(row[5])
            sqft = parse_float(row[4].split()[0])
            occupancy = parse_value(row[9])
            move_in = parse_date(row[21])
            lease_start = parse_date(row[23])
            lease_end = parse_date(row[20])
            rent_market = parse_float(row[10])
            rent_charge = parse_float(row[11])
            total_charge = parse_float(row[13])
            charge_codes = []
            for i in range(14, len(row), 3):
                if i + 2 < len(row):
                    charge_code = {
                        "code": parse_value(row[i]),
                        "scheduled_charge": parse_float(row[i + 1]),
                        "actual_charge": parse_float(row[i + 2]),
                    }
                    charge_codes.append(charge_code)
            json_output.append(
                {
                    "row_index": row_index,
                    "unit_num": unit_num,
                    "unit_type": unit_type,
                    "sqft": sqft,
                    "occupancy": occupancy,
                    "move_in": move_in,
                    "lease_start": lease_start,
                    "lease_end": lease_end,
                    "rent_market": rent_market,
                    "rent_charge": rent_charge,
                    "total_charge": total_charge,
                    "charge_codes": charge_codes,
                }
            )
        print(json.dumps(json_output, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <file_name>")
        sys.exit(1)
