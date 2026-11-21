import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Φόρτωση στοιχείων σύνδεσης από το .env
load_dotenv()
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# Ανάκτηση δεδομένων από τη MySQL
df_obs = pd.read_sql("SELECT * FROM macro_observations WHERE YEAR(observation_date) >= 2000", engine)
df_ind = pd.read_sql("SELECT indicator_id, indicator_code FROM indicators", engine)

df = df_obs.merge(df_ind, on="indicator_id")
df["year"] = pd.to_datetime(df["observation_date"]).dt.year

# Αυτόματος εντοπισμός της στήλης τιμών
exclude_cols = {"observation_id", "country_id", "indicator_id", "observation_date", "indicator_code", "year"}
val_col = [c for c in df.columns if c not in exclude_cols and pd.api.types.is_numeric_dtype(df[c])][0]

# Μετατροπή σε Wide format
df_wide = df.pivot(index=["country_id", "year"], columns="indicator_code", values=val_col).reset_index()

sns.set_theme(style="whitegrid")

# --- ΓΡΑΦΗΜΑ 1: Σύγκριση Κρίσεων (2008 GFC vs 2020 COVID-19) ---
focus_countries = ["GRC", "DEU", "ESP", "USA"]
df_crises = df_wide[(df_wide["country_id"].isin(focus_countries)) & (df_wide["year"] >= 2007)]

fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

sns.lineplot(data=df_crises, x="year", y="GDP_GROWTH_YOY", hue="country_id", marker="o", linewidth=2.2, ax=axes[0])
axes[0].axhline(0, color="black", linestyle="--", linewidth=1)
axes[0].axvspan(2008, 2013, color="gray", alpha=0.15, label="GFC & Eurozone Crisis")
axes[0].axvspan(2020, 2021, color="orange", alpha=0.15, label="COVID-19 Shock")
axes[0].set_title("Ρυθμός Μεταβολής ΑΕΠ (%) — Σύγκριση Κρίσεων (2007–2025)", fontsize=13, fontweight="bold")
axes[0].set_ylabel("GDP Growth (%)")
axes[0].legend(loc="lower left", ncol=3)

sns.lineplot(data=df_crises, x="year", y="UNEMP_RATE", hue="country_id", marker="s", linewidth=2.2, ax=axes[1])
axes[1].axvspan(2008, 2013, color="gray", alpha=0.15)
axes[1].axvspan(2020, 2021, color="orange", alpha=0.15)
axes[1].set_title("Ποσοστό Ανεργίας (%) — Διάρκεια & Ανάκαμψη Αγοράς Εργασίας", fontsize=13, fontweight="bold")
axes[1].set_ylabel("Unemployment Rate (%)")
axes[1].set_xlabel("Έτος")

plt.tight_layout()
plt.savefig("crisis_comparison.png", dpi=300)
plt.close()

# --- ΓΡΑΦΗΜΑ 2: Καμπύλη Phillips (Πληθωρισμός vs Ανεργία, 2000–2025) ---
df_phillips = df_wide[df_wide["country_id"] != "ARG"].dropna(subset=["CPI_INFLATION", "UNEMP_RATE"])

g = sns.lmplot(
    data=df_phillips,
    x="UNEMP_RATE",
    y="CPI_INFLATION",
    hue="country_id",
    height=6,
    aspect=1.5,
    scatter_kws={"alpha": 0.6, "s": 45},
    ci=None
)
plt.axhline(2.0, color="red", linestyle=":", linewidth=1.2, label="Στόχος Πληθωρισμού (2%)")
plt.title("Εμπειρική Καμπύλη Phillips: Πληθωρισμός vs Ανεργία (2000–2025)", fontsize=13, fontweight="bold")
plt.xlabel("Ποσοστό Ανεργίας (%)")
plt.ylabel("Πληθωρισμός CPI (%)")
plt.tight_layout()
plt.savefig("phillips_curve.png", dpi=300)
plt.close()

print("Ολοκληρώθηκε! Δημιουργήθηκαν τα αρχεία: crisis_comparison.png και phillips_curve.png")