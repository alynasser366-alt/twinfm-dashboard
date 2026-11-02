"""Twin-FM live dashboard (DIG521 Week 02) - Streamlit, deployable on Streamlit Community Cloud.

LIVE      : Madrid outdoor temperature + solar now, from Open-Meteo (no key, HTTPS, no cookies).
VIRTUAL   : 109 sensors of the Snowdon Towers twin. Their value = EnergyPlus free-running
            profile for this hour (typical 15 July) shifted by today's live outdoor anomaly,
            plus the front/back split from the comfort field. Labelled as simulated everywhere.
STATIC    : comfort LEVEL / DEPTH maps and the IoT mesh, exported from Revit + Python.
"""
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

HERE = Path(__file__).parent
D, IMG = HERE / "data", HERE / "img"
LAT, LON = 40.4168, -3.7038

st.set_page_config(page_title="Twin-FM · Snowdon Towers", page_icon="🏢", layout="wide")


@st.cache_data(ttl=600)
def live_weather():
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={LAT}&longitude={LON}&current=temperature_2m,shortwave_radiation,relative_humidity_2m"
           "&timezone=Europe%2FMadrid")
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)["current"]


@st.cache_data
def load():
    cal = pd.read_csv(D / "comfort_field_calibrated.csv", dtype={"number": str})
    sen = pd.read_csv(D / "sensors_revit.csv", dtype={"space": str})   # placed by Dynamo, exported from Revit
    yr = pd.read_parquet(D / "eplus_year.parquet")   # EnergyPlus full year, every space, every hour
    yr["number"] = yr.number.astype(str)
    return cal, sen, yr


cal, sen, yr = load()
now = datetime.now(ZoneInfo("Europe/Madrid"))
st.title("Twin-FM · Snowdon Towers digital twin")
st.caption("DIG521 Week 02 · Ali Nasser · Revit + Dynamo + EnergyPlus + Open-Meteo · "
           "sensor values are SIMULATED (virtual sensors), weather is LIVE")

# ---- live outdoor ------------------------------------------------------------
try:
    w = live_weather(); live_ok = True
except Exception as e:  # network down: keep the page usable
    w = {"temperature_2m": float("nan"), "shortwave_radiation": float("nan"), "relative_humidity_2m": float("nan")}
    live_ok = False
h = now.hour + 1                            # EnergyPlus hour 1..24 = hour ENDING (00:31 -> hour 1)
hr = yr[(yr.month == now.month) & (yr.day == min(now.day, 28 if now.month == 2 else now.day)) & (yr.hour == h)]
ref_out = hr.t_out.mean()
anomaly = (w["temperature_2m"] - ref_out) if live_ok else 0.0
sun = (w["shortwave_radiation"] / 800.0) if live_ok else 0.0   # front-back split only exists when the sun shines

c1, c2, c3, c4 = st.columns(4)
c1.metric("Madrid now (live)", f"{w['temperature_2m']:.1f} °C",
          f"{anomaly:+.1f} °C vs typical {now:%d %b} {now.hour:02d}:00", delta_color="off")
c2.metric("Solar radiation (live)", f"{w['shortwave_radiation']:.0f} W/m²")
c3.metric("Humidity (live)", f"{w['relative_humidity_2m']:.0f} %")
c4.metric("Virtual sensors", f"{len(sen)}", "10 floor gateways · mesh")
if not live_ok:
    st.warning("Open-Meteo not reachable right now: showing the typical-day profile only.")
st.info(f"How a reading is made: EnergyPlus room temperature for **{now:%d %B} at {now.hour:02d}:00** in a typical Madrid year "
        f"(free-running, no heating/AC) + half of today's live weather difference ({anomaly:+.1f} °C, the envelope "
        f"buffers the rest) + the front/back split scaled by live sun ({min(sun, 1):.0%}).")

# ---- virtual sensor readings for this hour ---------------------------------
room = hr[["number", "t_op"]].rename(columns={"t_op": "t_room"})
room["t_room"] = room.t_room + 0.5 * anomaly          # damped: the envelope buffers the outdoor swing
v = sen.merge(room, left_on="space", right_on="number", how="left").merge(
    cal[["number", "t_front", "t_back", "t_peak_mean"]], left_on="space", right_on="number", how="left", suffixes=("", "_c"))
k = min(max(sun, 0.0), 1.0)
split_f = (v.t_front - v.t_peak_mean).fillna(0) * k; split_b = (v.t_back - v.t_peak_mean).fillna(0) * k
v["reading_C"] = (v.t_room + (v.role == "FRONT") * split_f + (v.role == "BACK") * split_b).round(1)
# comfort bands (simplified from EN 16798-1 category II)
v["status"] = pd.cut(v.reading_C, [-99, 18, 20, 26, 28, 99],
                     labels=["cold", "cool", "comfortable", "warm", "overheating"])

st.subheader(f"Virtual sensor readings · {now:%H:%M} Madrid time")
lvls = sorted(v.level.unique())
pick = st.selectbox("Floor", lvls, index=lvls.index("L3") if "L3" in lvls else 0)
fv = v[v.level == pick][["space", "role", "facade", "reading_C", "status", "hop_m"]].sort_values("reading_C", ascending=False)
a, b = st.columns([3, 2])
a.dataframe(fv, hide_index=True, use_container_width=True,
            column_config={"reading_C": st.column_config.NumberColumn("°C (simulated)", format="%.1f"),
                           "hop_m": st.column_config.NumberColumn("mesh hop (m)", format="%.1f")})
out_of = int(fv.status.isin(["cold", "overheating"]).sum())
b.metric("Sensors out of comfort (cold or overheating)", out_of, f"of {len(fv)}", delta_color="off")
b.metric("Front-back split (mean)", f"{(split_f - split_b)[v.level == pick].mean():.1f} °C",
         help="How much hotter the sensor 1 m from the hottest facade is than the one at the back")
b.bar_chart(v.groupby("level").reading_C.mean().rename("mean °C per floor (simulated)"), height=220)

# ---- this space over the whole year (the twin's memory) -----------------------
st.subheader("One space through the year")
spc = st.selectbox("Space", sorted(v[v.level == pick].space.unique()))
yy = yr[yr.number == spc].groupby("month")[["t_op", "t_out"]].mean().rename(
    columns={"t_op": f"space {spc} (EnergyPlus, no AC)", "t_out": "outdoor Madrid (typical year)"})
st.line_chart(yy, height=240)
st.caption("Below ~20 °C the space needs heating, above ~26 °C cooling or shading: the twin shows WHEN and WHERE.")

# ---- maps ---------------------------------------------------------------------
st.subheader("Summer peak comfort maps from the model (15 July, worst case)")
fname = pick.replace(" ", "_")
t1, t2, t3 = st.tabs(["LEVEL (EnergyPlus)", "DEPTH (front → back)", "IoT mesh (L3)"])
for tab, pre in ((t1, "W2_comfort_field_"), (t2, "W2_depth_field_")):
    f = IMG / f"{pre}{fname}.jpg"
    if f.exists():
        tab.image(str(f), use_container_width=True)
    else:
        tab.info("No map for this floor (maps exist for L1 Block 37, L2–L5).")
t3.image(str(IMG / "W2_iot_L3.jpg"), use_container_width=True,
         caption="Red FRONT · blue BACK · grey INTERIOR · yellow GATEWAY · lines = mesh links (all ≤ 15 m; a star would need 29 links > 15 m)")

# ---- how it works + privacy ------------------------------------------------------
with st.expander("How the data flows (network + protocols)"):
    st.markdown("""
- **Sensor → gateway:** Thread / Zigbee mesh (IEEE 802.15.4, 2.4 GHz), IPv6 inside the mesh, one /27 per floor.
- **Gateway → cloud:** MQTT over TLS (port 8883), connection opened *outwards* because the building sits behind NAT.
- **Cloud → you:** this page over HTTPS (TLS 1.3); weather from the Open-Meteo REST API (JSON).
- **Cloud model:** PaaS (Streamlit Community Cloud) — the provider runs OS + runtime, Twin-FM owns code + data
  (shared responsibility).
""")
with st.expander("Privacy & cookies"):
    st.markdown("""
This dashboard sets **no tracking or advertising cookies** and stores **no personal data**: sensor data is
about rooms, not people. The hosting platform may use strictly necessary session cookies to keep the
websocket connection alive (exempt from consent under the ePrivacy Directive, Art. 5(3)).
""")
st.caption("Sources: Revit 2027 model (Snowdon Towers sample), EnergyPlus 24.1 via OpenStudio 3.8, "
           "Madrid TMYx 2009-2023 (climate.onebuilding.org), Open-Meteo API (CC BY 4.0).")
