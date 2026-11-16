"""Curated table of major U.S. airports. This contains a table of about 40 large airports instead of the
full OurAirports dataset. It covers the large majority of business travel and
lets city names map to all of a metro's airports which
is what enables the "consider an alternate airport" recommendation.
"""
from __future__ import annotations

# code: (name, city, lat, lon, icao, tz)
AIRPORTS: dict[str, tuple] = {
    "ATL": ("Hartsfield-Jackson Atlanta", "Atlanta", 33.6407, -84.4277, "KATL", "America/New_York"),
    "BOS": ("Boston Logan", "Boston", 42.3656, -71.0096, "KBOS", "America/New_York"),
    "BWI": ("Baltimore/Washington", "Baltimore", 39.1774, -76.6684, "KBWI", "America/New_York"),
    "CLT": ("Charlotte Douglas", "Charlotte", 35.2144, -80.9473, "KCLT", "America/New_York"),
    "DCA": ("Reagan Washington National", "Washington", 38.8512, -77.0402, "KDCA", "America/New_York"),
    "IAD": ("Washington Dulles", "Washington", 38.9531, -77.4565, "KIAD", "America/New_York"),
    "DTW": ("Detroit Metro", "Detroit", 42.2162, -83.3554, "KDTW", "America/Detroit"),
    "EWR": ("Newark Liberty", "New York", 40.6895, -74.1745, "KEWR", "America/New_York"),
    "JFK": ("John F. Kennedy", "New York", 40.6413, -73.7781, "KJFK", "America/New_York"),
    "LGA": ("LaGuardia", "New York", 40.7769, -73.8740, "KLGA", "America/New_York"),
    "FLL": ("Fort Lauderdale-Hollywood", "Fort Lauderdale", 26.0742, -80.1506, "KFLL", "America/New_York"),
    "MCO": ("Orlando International", "Orlando", 28.4312, -81.3081, "KMCO", "America/New_York"),
    "MIA": ("Miami International", "Miami", 25.7959, -80.2870, "KMIA", "America/New_York"),
    "PHL": ("Philadelphia International", "Philadelphia", 39.8744, -75.2424, "KPHL", "America/New_York"),
    "RDU": ("Raleigh-Durham", "Raleigh", 35.8801, -78.7880, "KRDU", "America/New_York"),
    "TPA": ("Tampa International", "Tampa", 27.9755, -82.5332, "KTPA", "America/New_York"),
    "BNA": ("Nashville International", "Nashville", 36.1263, -86.6774, "KBNA", "America/Chicago"),
    "ORD": ("Chicago O'Hare", "Chicago", 41.9742, -87.9073, "KORD", "America/Chicago"),
    "MDW": ("Chicago Midway", "Chicago", 41.7868, -87.7522, "KMDW", "America/Chicago"),
    "DFW": ("Dallas/Fort Worth", "Dallas", 32.8998, -97.0403, "KDFW", "America/Chicago"),
    "DAL": ("Dallas Love Field", "Dallas", 32.8471, -96.8518, "KDAL", "America/Chicago"),
    "IAH": ("Houston Bush Intercontinental", "Houston", 29.9902, -95.3368, "KIAH", "America/Chicago"),
    "HOU": ("Houston Hobby", "Houston", 29.6454, -95.2789, "KHOU", "America/Chicago"),
    "AUS": ("Austin-Bergstrom", "Austin", 30.1975, -97.6664, "KAUS", "America/Chicago"),
    "MSP": ("Minneapolis-St. Paul", "Minneapolis", 44.8848, -93.2223, "KMSP", "America/Chicago"),
    "STL": ("St. Louis Lambert", "St. Louis", 38.7499, -90.3748, "KSTL", "America/Chicago"),
    "DEN": ("Denver International", "Denver", 39.8561, -104.6737, "KDEN", "America/Denver"),
    "SLC": ("Salt Lake City", "Salt Lake City", 40.7899, -111.9791, "KSLC", "America/Denver"),
    "PHX": ("Phoenix Sky Harbor", "Phoenix", 33.4342, -112.0116, "KPHX", "America/Phoenix"),
    "LAS": ("Harry Reid Las Vegas", "Las Vegas", 36.0840, -115.1537, "KLAS", "America/Los_Angeles"),
    "LAX": ("Los Angeles International", "Los Angeles", 33.9416, -118.4085, "KLAX", "America/Los_Angeles"),
    "SAN": ("San Diego International", "San Diego", 32.7338, -117.1933, "KSAN", "America/Los_Angeles"),
    "SFO": ("San Francisco International", "San Francisco", 37.6213, -122.3790, "KSFO", "America/Los_Angeles"),
    "OAK": ("Oakland International", "San Francisco", 37.7126, -122.2197, "KOAK", "America/Los_Angeles"),
    "SJC": ("San Jose Mineta", "San Francisco", 37.3639, -121.9289, "KSJC", "America/Los_Angeles"),
    "SEA": ("Seattle-Tacoma", "Seattle", 47.4502, -122.3088, "KSEA", "America/Los_Angeles"),
    "PDX": ("Portland International", "Portland", 45.5898, -122.5951, "KPDX", "America/Los_Angeles"),
    "ANC": ("Ted Stevens Anchorage", "Anchorage", 61.1743, -149.9983, "PANC", "America/Anchorage"),
    "HNL": ("Daniel K. Inouye Honolulu", "Honolulu", 21.3245, -157.9251, "PHNL", "Pacific/Honolulu"),
}

CITY_ALIASES = {
    "nyc": "New York", "new york city": "New York", "manhattan": "New York",
    "sf": "San Francisco", "bay area": "San Francisco", "silicon valley": "San Francisco",
    "la": "Los Angeles", "dc": "Washington", "washington dc": "Washington",
    "vegas": "Las Vegas", "dfw": "Dallas", "fort worth": "Dallas", "philly": "Philadelphia",
    "twin cities": "Minneapolis", "san jose": "San Francisco", "oakland": "San Francisco",
}


def info(code: str) -> dict:
    name, city, lat, lon, icao, tz = AIRPORTS[code]
    return {"code": code, "name": name, "city": city, "lat": lat, "lon": lon, "icao": icao, "tz": tz}


def resolve(text: str) -> list[str]:
    """Resolve 'JFK', 'New York', or 'nyc' to a list of airport codes."""
    t = text.strip()
    if t.upper() in AIRPORTS:
        return [t.upper()]
    city = CITY_ALIASES.get(t.lower(), t)
    return [c for c, v in AIRPORTS.items() if v[1].lower() == city.lower()]


def catalog_for_prompt() -> str:
    return "\n".join(f"{c}: {v[0]} ({v[1]})" for c, v in AIRPORTS.items())
