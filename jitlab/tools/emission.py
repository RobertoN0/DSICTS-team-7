import requests
import datetime
import json
import sys
import os
import argparse

# ---------------------------
# Configuration
# ---------------------------
API_KEY = "your-api-key"
USER_AGENT = "Design Sustainable ICT Systems"
BASE_URL = "https://www.nowtricity.com/api"


def get_emissions_last_24h(country_id: str, output_dir: str):
    """Fetch emissions data for the last 24 hours from Nowtricity API and save JSON file."""
    url = f"{BASE_URL}/emissions-previous-24h/{country_id}/"
    headers = {
        "X-Api-Key": API_KEY,
        "User-Agent": USER_AGENT
    }

    print(f"Fetching emissions for '{country_id}' from Nowtricity...")
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Error: Failed to fetch data ({response.status_code})")
        print(response.text)
        sys.exit(1)

    data = response.json()

    # Prepare filename and save directory
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    filename = os.path.join(output_dir, f"emissions_{country_id}_{timestamp}.json")

    # Save JSON data
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    print(f"Data saved to {filename}")

    # Extract and print emissions
    emissions = data.get("emissions", [])
    if not emissions:
        print("No emission data found for the last 24 hours.")
        return

    print(f"\nEmission data for {data['country']['name']} (last 24h):\n")
    for entry in emissions:
        local_time = entry["dateLocal"]
        value = entry["value"]
        unit = entry["unit"]
        print(f"{local_time}: {value} {unit}")

    # Average emissions
    avg = sum(e["value"] for e in emissions) / len(emissions)
    print(f"\nAverage emissions over the last 24h: {avg:.2f} {emissions[0]['unit']}\n")


def main():
    parser = argparse.ArgumentParser(description="Fetch and save last 24h electricity emissions data from Nowtricity API.")
    parser.add_argument("country_id", help="Country ID (e.g. 'norway', 'france', 'germany')")
    parser.add_argument("-o", "--output", default="emission-data", help="Output directory for saved JSON file (default: ./data)")
    args = parser.parse_args()

    get_emissions_last_24h(args.country_id, args.output)


if __name__ == "__main__":
    main()
