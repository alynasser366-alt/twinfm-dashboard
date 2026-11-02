# Twin-FM · Snowdon Towers digital twin (DIG521 Week 02)

Live dashboard of a small building digital twin built by an architect:
Revit model → EnergyPlus comfort analysis → Dynamo sensor placement → IoT mesh → this page.

- **Live:** Madrid weather from the Open-Meteo API.
- **Simulated:** 109 virtual sensors (FRONT near the hottest facade, BACK deep in the room, INTERIOR),
  values from an EnergyPlus free-running summer run of the Revit model.
- **No tracking cookies, no personal data.**

Run locally: `pip install -r requirements.txt` then `streamlit run app.py`.

Sources: Snowdon Towers (Autodesk Revit 2027 sample), EnergyPlus 24.1 / OpenStudio 3.8,
Madrid TMYx 2009-2023 (climate.onebuilding.org), Open-Meteo (CC BY 4.0).
