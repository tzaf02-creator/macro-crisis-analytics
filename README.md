# Macroeconomic Crisis Analytics & Phillips Curve Pipeline

An end-to-end **Data Engineering & Econometric Analysis** portfolio project that extracts historical macroeconomic indicators from the **World Bank API**, loads them into a normalized **MySQL 8.0** relational database, and performs comparative crisis analytics and empirical **Phillips Curve** modeling in **Python**.

---

## Project Architecture & Tech Stack

* **Database:** MySQL 8.0 (3rd Normal Form schema with foreign key constraints and composite indexing)
* **ETL Pipeline:** Python (`requests`, `SQLAlchemy`, `PyMySQL`, `python-dotenv`)
* **Data Analysis & Visualization:** `pandas`, `matplotlib`, `seaborn`
* **Data Source:** World Bank Open Data API (`1990–2025`, 8 economies, 3 core indicators, 826 verified observations)

### Repository Structure
```text
macro-crisis-analytics/
├── etl_world_bank.py         # Automated ETL script fetching & upserting World Bank data into MySQL
├── macro_analysis.py         # SQL-to-Pandas econometric analysis & visualization generator
├── crisis_comparison.png     # GDP growth & unemployment trajectories (2008 GFC vs. 2020 COVID-19)
├── phillips_curve.png        # Empirical inflation-unemployment trade-off across regimes (2000–2025)
├── .gitignore                # Excludes .env credentials from version control
└── README.md                 # Project documentation & econometric findings