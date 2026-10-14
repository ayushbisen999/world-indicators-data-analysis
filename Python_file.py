import numpy as np
import pandas as pd
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Setup resilient session ---
session = requests.Session()
retry = Retry(
    total=5,                # retry up to 5 times
    backoff_factor=2,       # wait 2, 4, 8... seconds between retries
    status_forcelist=[500, 502, 503, 504],
    raise_on_status=False
)
adapter = HTTPAdapter(max_retries=retry)
session.mount("http://", adapter)
session.mount("https://", adapter)

def safe_get(url):
    try:
        return session.get(url, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

# --- Fetch countries ---
countries_url = "https://api.worldbank.org/v2/countries?format=json&per_page=300"
response = safe_get(countries_url)
countries_data = response.json()
countries = pd.DataFrame(countries_data[1])
countries['region'] = countries['region'].apply(lambda x: x["value"])
countries['incomeLevel'] = countries['incomeLevel'].apply(lambda x: x["value"])
countries['lendingType'] = countries['lendingType'].apply(lambda x: x["value"])
countries.rename(columns={"iso2Code": "country_id"}, inplace=True)
countries.drop(columns=["adminregion"], inplace=True)

# --- Indicator groups ---
indicator_groups = {
    "economic_activity_growth": [
        "NY.GDP.MKTP.KD.ZG",  # GDP growth (annual %)
        "NY.GDP.PCAP.CD"      # GDP per capita (current US$)
    ],

    "labour_market_indicators": [
        "SL.UEM.TOTL.ZS",      # Unemployment total
        "SL.UEM.1524.ZS",      # Unemployment youth total (ages 15–24)
        "SL.TLF.TOTL.IN"       # Labour force, total
    ],

    "trade_globalization": [
        "NE.EXP.GNFS.CD",      # Exports of goods and services (current US$)
        "NE.IMP.GNFS.CD"       # Imports of goods and services (current US$)
    ],

    "poverty_inequality": [
        "SI.POV.NAHC",         # Poverty headcount ratio at national poverty lines (% of population)
        "SI.POV.GINI"          # Gini index (income inequality)
    ],

    "environmental_indicators": [
        "EG.FEC.RNEW.ZS",      # Renewable energy consumption (% of total final energy consumption)
        "AG.LND.FRST.ZS"       # Forest area (% of land area)
    ],

    "health_indicators": [
        "SP.DYN.LE00.IN",      # Life expectancy at birth
        "SP.DYN.IMRT.IN",      # Infant mortality rate
        "SH.H2O.BASH.ZS",      # Access to basic water services (% of population)
        "SH.XPD.CHEX.GD.ZS",   # Health expenditure (% of GDP)
        "SH.IMM.IDPT",         # Immunization, DPT (% of children ages 12–23 months)
        "SH.IMM.MEAS",         # Immunization, measles (% of children ages 12–23 months)
        "SH.MMR.RISK.ZS",      # Risk of maternal death
        "SH.DTH.COMM.ZS",      # Deaths from communicable diseases (% of total)
        "SH.TBS.INCD",         # Tuberculosis incidence (per 100,000 people)
        "SH.STA.BRTC.ZS",      # Births attended by skilled health staff (%)
        "SH.STA.MMRT",         # Maternal mortality ratio (per 100,000 live births)
        "SP.POP.65UP.TO.ZS",   # Population ages 65+ (% of total)
        "SH.HIV.INCD.ZS"       # HIV incidence rate (per 1,000 uninfected ages 15–49)
    ],

    "technology_indicators": [
        "IT.NET.USER.ZS",      # Internet users (% of population)
        "IT.CEL.SETS.P2"       # Mobile cellular subscriptions (per 100 people)
    ]
}


base_url = "https://api.worldbank.org/v2/countries/all/indicators/{}?format=json&per_page=200&page={}"
category_dataframes = {}

# --- Fetch indicators ---
for category, indicators in indicator_groups.items():
    print(f"Fetching data for category: {category}")
    all_dfs_for_category = []

    for indicator_code in indicators:
        print(f"Fetching indicator: {indicator_code}")
        page = 1

        while True:
            url = base_url.format(indicator_code, page)
            response = safe_get(url)
            if not response or response.status_code != 200:
                print(f"Failed to fetch {indicator_code} page {page}")
                break

            data = response.json()
            if len(data) < 2:
                print(f"No more data for {indicator_code} page {page}")
                break

            total_pages = data[0]["pages"]
            record = data[1]

            df = pd.json_normalize(record)
            df = df[["country.id","country.value","indicator.id","indicator.value","date","value"]].rename(
                columns={
                    "country.id": "country_id",
                    "country.value": "country_name",
                    "indicator.id": "indicator_code",
                    "indicator.value": "indicator_name",
                    "date": "year"
                }
            )
            df = df[df["year"].astype(int) > 2015]
            all_dfs_for_category.append(df)

            if page >= total_pages:
                break
            else:
                page += 1
                time.sleep(3)  # gentler delay

    if all_dfs_for_category:
        combined_df = pd.concat(all_dfs_for_category, ignore_index=True)
        category_dataframes[category] = combined_df
        print(f"Data for {category}: {len(combined_df)} rows")
    else:
        print(f"No data found for {category}")

# --- Merge with countries ---
def merge_and_clean(df, countries):
    if df.empty:
        return df
    merged = pd.merge(df, countries, on="country_id", how="inner")
    return merged.drop(columns=["indicator_code","name","id"], errors="ignore")

economic = merge_and_clean(category_dataframes.get("economic_activity_growth", pd.DataFrame()), countries)
labour_market = merge_and_clean(category_dataframes.get("labour_market_indicators", pd.DataFrame()), countries)
trade = merge_and_clean(category_dataframes.get("trade_globalization", pd.DataFrame()), countries)
poverty = merge_and_clean(category_dataframes.get("poverty_inequality", pd.DataFrame()), countries)
environment = merge_and_clean(category_dataframes.get("environmental_indicators", pd.DataFrame()), countries)
health = merge_and_clean(category_dataframes.get("health_indicators", pd.DataFrame()), countries)
technology = merge_and_clean(category_dataframes.get("technology_indicators", pd.DataFrame()), countries)

print("Dataframes ready:", list(category_dataframes.keys()))


