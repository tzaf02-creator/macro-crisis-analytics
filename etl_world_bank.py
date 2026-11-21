import logging
import os
from typing import Dict, List, Any

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

# =========================================================================
# 1. ΡΥΘΜΙΣΕΙΣ LOGGING & ΠΑΡΑΜΕΤΡΟΙ ETL
# =========================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

START_YEAR = 1990
END_YEAR = 2025
WB_API_BASE_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{wb_code}"

# Χώρες προς φόρτωση (Πλήρης συμβατότητα με το ENUM income_group της βάσης)
COUNTRIES_METADATA = [
    {"country_id": "GRC", "country_name": "Greece",         "region": "Europe & Central Asia", "income_group": "HIGH",         "current_currency": "EUR"},
    {"country_id": "USA", "country_name": "United States",  "region": "North America",         "income_group": "HIGH",         "current_currency": "USD"},
    {"country_id": "DEU", "country_name": "Germany",        "region": "Europe & Central Asia", "income_group": "HIGH",         "current_currency": "EUR"},
    {"country_id": "ESP", "country_name": "Spain",          "region": "Europe & Central Asia", "income_group": "HIGH",         "current_currency": "EUR"},
    {"country_id": "ITA", "country_name": "Italy",          "region": "Europe & Central Asia", "income_group": "HIGH",         "current_currency": "EUR"},
    {"country_id": "GBR", "country_name": "United Kingdom", "region": "Europe & Central Asia", "income_group": "HIGH",         "current_currency": "GBP"},
    {"country_id": "JPN", "country_name": "Japan",          "region": "East Asia & Pacific",   "income_group": "HIGH",         "current_currency": "JPY"},
    {"country_id": "ARG", "country_name": "Argentina",      "region": "Latin America & Caribbean", "income_group": "UPPER_MIDDLE", "current_currency": "ARS"},
]

# Αντιστοίχιση κωδικών World Bank API -> Πίνακας indicators της βάσης μας
INDICATORS_CONFIG = [
    {
        "wb_code": "NY.GDP.MKTP.KD.ZG",
        "indicator_code": "GDP_GROWTH_YOY",
        "indicator_name": "Real GDP Growth (Annual %)",
        "unit": "Percent",
        "frequency": "ANNUAL",
        "data_source": "World Bank API"
    },
    {
        "wb_code": "FP.CPI.TOTL.ZG",
        "indicator_code": "CPI_INFLATION",
        "indicator_name": "Inflation, Consumer Prices (Annual %)",
        "unit": "Percent",
        "frequency": "ANNUAL",
        "data_source": "World Bank API"
    },
    {
        "wb_code": "SL.UEM.TOTL.ZS",
        "indicator_code": "UNEMP_RATE",
        "indicator_name": "Unemployment, Total (% of labor force, ILO est.)",
        "unit": "Percent",
        "frequency": "ANNUAL",
        "data_source": "World Bank API"
    },
]


# =========================================================================
# 2. ΣΥΝΔΕΣΗ ΜΕ MYSQL (SQLAlchemy 2.0)
# =========================================================================
def get_db_engine() -> Engine:
    """Δημιουργεί ασφαλές SQLAlchemy Engine από μεταβλητές περιβάλλοντος."""
    load_dotenv()

    connection_url = URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        database=os.getenv("DB_NAME", "macro_crisis_analytics"),
        query={"charset": "utf8mb4"}
    )
    return create_engine(connection_url, pool_pre_ping=True)


# =========================================================================
# 3. LOAD DIMENSIONS (Χώρες & Δείκτες με Idempotent UPSERT)
# =========================================================================
def sync_dimensions(engine: Engine) -> Dict[str, int]:
    """
    Εισάγει/ενημερώνει τις χώρες και τους δείκτες στη βάση
    και επιστρέφει mapping {indicator_code: indicator_id}.
    """
    upsert_countries_sql = text("""
        INSERT INTO countries (country_id, country_name, region, income_group, current_currency)
        VALUES (:country_id, :country_name, :region, :income_group, :current_currency)
        AS new_row
        ON DUPLICATE KEY UPDATE
            country_name     = new_row.country_name,
            region           = new_row.region,
            income_group     = new_row.income_group,
            current_currency = new_row.current_currency;
    """)

    upsert_indicators_sql = text("""
        INSERT INTO indicators (indicator_code, indicator_name, unit, frequency, data_source)
        VALUES (:indicator_code, :indicator_name, :unit, :frequency, :data_source)
        AS new_row
        ON DUPLICATE KEY UPDATE
            indicator_name = new_row.indicator_name,
            unit           = new_row.unit,
            data_source    = new_row.data_source;
    """)

    select_indicators_sql = text("SELECT indicator_code, indicator_id FROM indicators;")

    with engine.begin() as conn:
        conn.execute(upsert_countries_sql, COUNTRIES_METADATA)
        conn.execute(upsert_indicators_sql, INDICATORS_CONFIG)
        rows = conn.execute(select_indicators_sql).fetchall()

    indicator_map = {row[0]: row[1] for row in rows}
    logger.info(f"Συγχρονίστηκαν {len(COUNTRIES_METADATA)} χώρες και {len(INDICATORS_CONFIG)} δείκτες.")
    return indicator_map


# =========================================================================
# 4. EXTRACT: Κλήση World Bank API v2 με Pagination
# =========================================================================
def fetch_wb_indicator(
    wb_code: str,
    country_ids: List[str],
    start_year: int,
    end_year: int
) -> List[Dict[str, Any]]:
    """Τραβάει όλες τις σελίδες δεδομένων από το World Bank API για έναν δείκτη."""
    countries_param = ";".join(country_ids)
    url = WB_API_BASE_URL.format(countries=countries_param, wb_code=wb_code)

    all_records: List[Dict[str, Any]] = []
    page = 1

    while True:
        params = {
            "date": f"{start_year}:{end_year}",
            "format": "json",
            "per_page": 1000,
            "page": page
        }
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()

        # Το World Bank API επιστρέφει λίστα [metadata, data]
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            logger.warning(f"Δεν βρέθηκαν δεδομένα για τον δείκτη {wb_code}.")
            break

        metadata, data = payload[0], payload[1]
        all_records.extend(data)

        total_pages = int(metadata.get("pages", 1))
        if page >= total_pages:
            break
        page += 1

    logger.info(f"Extract [{wb_code}]: Ανακτήθηκαν {len(all_records)} ακατέργαστες εγγραφές.")
    return all_records


# =========================================================================
# 5. TRANSFORM: Καθαρισμός & Τυποποίηση
# =========================================================================
def transform_observations(
    raw_records: List[Dict[str, Any]],
    indicator_id: int,
    valid_countries: set
) -> List[Dict[str, Any]]:
    """Φιλτράρει NULL τιμές και μορφοποιεί ημερομηνίες/δεκαδικά για τη MySQL."""
    cleaned: List[Dict[str, Any]] = []

    for rec in raw_records:
        val = rec.get("value")
        iso3 = rec.get("countryiso3code")
        year_str = rec.get("date")

        # Αγνοούμε κενές παρατηρήσεις (π.χ. έτη που δεν έχουν δημοσιευτεί ακόμη)
        if val is None or iso3 not in valid_countries or not year_str:
            continue

        cleaned.append({
            "country_id": iso3,
            "indicator_id": indicator_id,
            "observation_date": f"{year_str}-01-01",  # Πρότυπο 1ης ημέρας του έτους
            "obs_value": round(float(val), 4)         # Ακρίβεια DECIMAL(18, 4)
        })

    return cleaned


# =========================================================================
# 6. LOAD FACTS: Μαζική Εισαγωγή (Bulk Upsert)
# =========================================================================
def load_observations(engine: Engine, records: List[Dict[str, Any]]) -> int:
    """Εισάγει ή ενημερώνει μαζικά παρατηρήσεις στον πίνακα macro_observations."""
    if not records:
        return 0

    upsert_obs_sql = text("""
        INSERT INTO macro_observations (country_id, indicator_id, observation_date, obs_value)
        VALUES (:country_id, :indicator_id, :observation_date, :obs_value)
        AS new_row
        ON DUPLICATE KEY UPDATE
            obs_value = new_row.obs_value;
    """)

    with engine.begin() as conn:
        conn.execute(upsert_obs_sql, records)

    return len(records)


# =========================================================================
# 7. ΚΥΡΙΑ ΡΟΗ ETL
# =========================================================================
def run_etl() -> None:
    logger.info("Έναρξη ETL pipeline για macro_crisis_analytics...")
    engine = get_db_engine()

    # 1. Συγχρονισμός διαστάσεων (Countries & Indicators)
    indicator_map = sync_dimensions(engine)
    country_ids = [c["country_id"] for c in COUNTRIES_METADATA]
    valid_countries_set = set(country_ids)

    total_loaded = 0

    # 2. Extract -> Transform -> Load για κάθε δείκτη
    for ind in INDICATORS_CONFIG:
        wb_code = ind["wb_code"]
        ind_code = ind["indicator_code"]
        ind_id = indicator_map[ind_code]

        try:
            raw_data = fetch_wb_indicator(wb_code, country_ids, START_YEAR, END_YEAR)
            clean_data = transform_observations(raw_data, ind_id, valid_countries_set)
            loaded_count = load_observations(engine, clean_data)

            total_loaded += loaded_count
            logger.info(f"Load    [{ind_code}]: Ενημερώθηκαν/εισήχθησαν {loaded_count} παρατηρήσεις.")

        except requests.RequestException as e:
            logger.error(f"Σφάλμα δικτύου/API για τον δείκτη {wb_code}: {e}")
        except Exception as e:
            logger.error(f"Απρόσμενο σφάλμα στον δείκτη {ind_code}: {e}", exc_info=True)

    logger.info(f"Ολοκλήρωση ETL! Συνολικές εγγραφές που επεξεργάστηκαν: {total_loaded}")


if __name__ == "__main__":
    run_etl()