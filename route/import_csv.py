import os
import pandas as pd
from route.models import FuelStop  # Replace with your actual app name
from django.conf import settings

# Get the absolute path of the CSV file
BASE_DIR = settings.BASE_DIR  
CSV_PATH = os.path.join(BASE_DIR, "data", "fuel-prices-for-be-assessment.csv")

def import_csv():
    if not os.path.exists(CSV_PATH):
        print("❌ CSV file not found:", CSV_PATH)
        return

    df = pd.read_csv(CSV_PATH)

    # Convert Retail Price to numeric (handling errors)
    df["Retail Price"] = pd.to_numeric(df["Retail Price"], errors="coerce")

    # Group by OPIS Truckstop ID, take the first entry for details, and compute the average price
    df = df.groupby("OPIS Truckstop ID").agg({
        "Truckstop Name": "first",
        "Address": "first",
        "City": "first",
        "State": "first",
        "Rack ID": "first",
        "Retail Price": "mean"  # Compute the average price
    }).reset_index()

    # Insert into database
    for _, row in df.iterrows():
        FuelStop.objects.update_or_create(
            opis_id=row["OPIS Truckstop ID"],
            defaults={
                "name": row["Truckstop Name"],
                "address": row["Address"],
                "city": row["City"],
                "state": row["State"],
                "rack_id": row["Rack ID"],
                "retail_price": row["Retail Price"],  # Average price
            },
        )

    print(f"✅ {len(df)} unique fuel stops imported successfully!")

if __name__ == "__main__":
    import_csv()
