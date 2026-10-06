import html
import math
import os
import re

import folium
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

# Load environment variables from .env (optional): HF_TOKEN, APP_CONTACT
load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# Nominatim's usage policy requires an identifying User-Agent.
# Put your own email in .env as APP_CONTACT, or edit the default below.
APP_CONTACT = os.getenv("APP_CONTACT", "your-email@example.com")
HEADERS = {"User-Agent": f"travel-recommendation-demo/1.0 ({APP_CONTACT})"}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Public Overpass servers are sometimes busy; we try them in order.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Generic Hugging Face router: it picks any provider that serves the model.
HF_API_URL = "https://router.huggingface.co/v1/chat/completions"
# Tried in order; if one is not available for your account, the next is used.
# You can also pin a provider with a suffix, e.g. "Qwen/Qwen2.5-7B-Instruct:cheapest".
HF_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen3-8B",
    "meta-llama/Llama-3.1-8B-Instruct",
]

CATEGORIES = {
    "Hotel": {
        "label": "Hotels 🏨",
        "filter": '["tourism"~"^(hotel|guest_house|hostel|motel|apartment)$"]',
        "color": "blue",
        "icon": "home",
    },
    "Restaurant": {
        "label": "Restaurants 🍴",
        "filter": '["amenity"~"^(restaurant|cafe|food_court)$"]',
        "color": "green",
        "icon": "cutlery",
    },
    "Tourist": {
        "label": "Tourist Attractions ⭐",
        "filter": '["tourism"~"^(attraction|museum|gallery|viewpoint|zoo|theme_park|aquarium)$"]',
        "color": "orange",
        "icon": "star",
    },
}

COLUMNS = [
    "Type", "Name", "Category", "Distance (km)", "Address", "Phone",
    "Website", "OpenStreetMap URL", "Latitude", "Longitude",
]


# ---------------------------------------------------------------------------
# OpenStreetMap helpers
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@st.cache_data(show_spinner=False, ttl=3600)
def geocode(destination):
    """Destination text -> {'lat', 'lon', 'name'} or None. Uses Nominatim."""
    r = requests.get(
        NOMINATIM_URL,
        params={"q": destination, "format": "jsonv2", "limit": 1},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    return {
        "lat": float(data[0]["lat"]),
        "lon": float(data[0]["lon"]),
        "name": data[0].get("display_name", destination),
    }


def overpass_request(query):
    """Send a query to the Overpass servers, falling back to the next on failure."""
    last_error = None
    for endpoint in OVERPASS_URLS:
        try:
            r = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=40)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last_error = e
    raise RuntimeError(f"All Overpass servers failed or are busy ({last_error})")


def build_address(tags):
    street = " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")]))
    parts = [street, tags.get("addr:suburb"), tags.get("addr:city"), tags.get("addr:postcode")]
    return ", ".join(p for p in parts if p) or "N/A"


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_places(lat, lon, radius, place_type, limit):
    """Named places of one category around a point, nearest first.

    Exceptions are not cached by Streamlit, so a failed call is retried next run.
    """
    query = (
        "[out:json][timeout:25];"
        f'nwr{CATEGORIES[place_type]["filter"]}["name"](around:{int(radius)},{lat},{lon});'
        "out center 150;"
    )
    elements = overpass_request(query).get("elements", [])

    rows = []
    for e in elements:
        tags = e.get("tags", {})
        la = e.get("lat") or e.get("center", {}).get("lat")
        lo = e.get("lon") or e.get("center", {}).get("lon")
        if la is None or lo is None or not tags.get("name"):
            continue
        kind = tags.get("tourism") or tags.get("amenity") or ""
        rows.append({
            "Type": place_type,
            "Name": tags["name"],
            "Category": kind.replace("_", " ").title(),
            "Distance (km)": round(haversine_km(lat, lon, la, lo), 2),
            "Address": build_address(tags),
            "Phone": tags.get("phone") or tags.get("contact:phone") or "N/A",
            "Website": tags.get("website") or tags.get("contact:website") or "N/A",
            "OpenStreetMap URL": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
            "Latitude": la,
            "Longitude": lo,
        })

    if not rows:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["Name", "Latitude", "Longitude"])
    df = df.sort_values("Distance (km)").head(int(limit)).reset_index(drop=True)
    return df[COLUMNS]


# ---------------------------------------------------------------------------
# Map / list rendering
# ---------------------------------------------------------------------------
def render_map(df, center, place_type, destination):
    cfg = CATEGORIES[place_type]
    m = folium.Map(location=[center["lat"], center["lon"]], zoom_start=13, control_scale=True)

    folium.Marker(
        [center["lat"], center["lon"]],
        tooltip="Search centre",
        icon=folium.Icon(color="red", icon="flag"),
    ).add_to(m)

    points = [[center["lat"], center["lon"]]]
    for _, row in df.iterrows():
        popup_html = (
            f"<b>{html.escape(str(row['Name']))}</b><br>"
            f"{html.escape(str(row['Category']))} · {row['Distance (km)']} km<br>"
            f"{html.escape(str(row['Address']))}<br>"
            f"<a href='{html.escape(str(row['OpenStreetMap URL']))}' target='_blank'>View on OpenStreetMap</a>"
        )
        folium.Marker(
            [row["Latitude"], row["Longitude"]],
            tooltip=str(row["Name"]),
            popup=folium.Popup(folium.IFrame(popup_html, width=280, height=130), max_width=300),
            icon=folium.Icon(color=cfg["color"], icon=cfg["icon"]),
        ).add_to(m)
        points.append([row["Latitude"], row["Longitude"]])

    if len(points) > 1:
        m.fit_bounds(points, padding=(30, 30))

    st_folium(m, height=480, returned_objects=[], key=f"map_{place_type}_{destination}")


def render_list(df):
    for i, row in df.iterrows():
        st.markdown(f"**{i + 1}. {row['Name']}** — {row['Category']} · {row['Distance (km)']} km away")
        st.write(f"Address: {row['Address']}")
        if row["Phone"] != "N/A":
            st.write(f"Phone: {row['Phone']}")
        if row["Website"] != "N/A":
            st.write(f"Website: {row['Website']}")
        st.write(f"More information: {row['OpenStreetMap URL']}")
        st.divider()


# ---------------------------------------------------------------------------
# Data loading shared by the Search and Database pages
# ---------------------------------------------------------------------------
def load_all(destination, radius, limit):
    """Returns (center, {type: df}, errors) or (None, {}, errors) if geocoding fails."""
    errors = []
    try:
        center = geocode(destination)
    except requests.RequestException as e:
        st.error(f"⚠️ Could not reach the geocoding service (Nominatim): {e}")
        return None, {}, errors
    if center is None:
        st.error("⚠️ No location results returned. Try a different destination.")
        return None, {}, errors

    results = {}
    with st.spinner("Finding places near your destination..."):
        for place_type in CATEGORIES:
            try:
                results[place_type] = fetch_places(center["lat"], center["lon"], radius, place_type, limit)
            except Exception as e:
                results[place_type] = pd.DataFrame(columns=COLUMNS)
                errors.append(f"{CATEGORIES[place_type]['label']}: {e}")

    # Remember a short summary so the chatbot can use real data
    lines = [f"Destination: {center['name']}"]
    for place_type, df in results.items():
        if not df.empty:
            names = ", ".join(df["Name"].head(5))
            lines.append(f"{CATEGORIES[place_type]['label']} nearby: {names}")
    st.session_state["places_context"] = "\n".join(lines)

    return center, results, errors


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def search_page(destination, radius, limit):
    st.header("🌏 Travel Recommendation App 🌏")
    if not destination:
        st.info("Enter a destination in the sidebar to get started.")
        return

    center, results, errors = load_all(destination, radius, limit)
    if center is None:
        return
    for err in errors:
        st.warning(f"Could not load {err}")

    places_label = st.radio("Looking for: ", [c["label"] for c in CATEGORIES.values()])
    place_type = next(k for k, v in CATEGORIES.items() if v["label"] == places_label)
    df = results[place_type]

    st.write(f"# Here are our recommendations for {places_label} near {destination}")
    if df.empty:
        st.info("No places found. Try a larger search radius or a different destination.")
        return

    render_map(df, center, place_type, destination)
    render_list(df)


def database_page(destination, radius, limit):
    st.header("📑 Database")
    if not destination:
        st.info("Enter a destination in the sidebar to get started.")
        return

    center, results, errors = load_all(destination, radius, limit)
    if center is None:
        return
    for err in errors:
        st.warning(f"Could not load {err}")

    frames = [df for df in results.values() if not df.empty]
    if not frames:
        st.info("No places found. Try a larger search radius or a different destination.")
        return

    df_all = pd.concat(frames, ignore_index=True).sort_values("Distance (km)").reset_index(drop=True)
    st.dataframe(
        df_all,
        column_config={
            "Website": st.column_config.LinkColumn("Website"),
            "OpenStreetMap URL": st.column_config.LinkColumn("OpenStreetMap URL"),
        },
    )
    st.download_button(
        "Download as CSV",
        df_all.to_csv(index=False).encode("utf-8"),
        file_name="places.csv",
        mime="text/csv",
    )


def hf_query(messages, hf_token):
    """Call the Hugging Face router, trying each model in HF_MODELS.

    Returns parsed JSON or None (error shown in the UI).
    """
    last_error = "unknown error"
    for model in HF_MODELS:
        try:
            response = requests.post(
                HF_API_URL,
                headers={"Authorization": f"Bearer {hf_token}"},
                json={"model": model, "messages": messages},
                timeout=90,
            )
        except requests.RequestException as e:
            st.error(f"Request failed: {e}")
            return None

        if response.ok:
            try:
                return response.json()
            except ValueError:
                last_error = f"{model}: invalid JSON in response"
                continue

        last_error = f"{model}: HTTP {response.status_code} {response.text[:300]}"
        if response.status_code in (401, 403):  # token problem: other models won't help
            break
        # 400/404 (model not supported), 429, 5xx: try the next model

    st.error(f"Chat request failed. Last error: {last_error}")
    return None


def extract_reply(resp):
    """Pull the answer text out of the response, dropping any reasoning blocks."""
    content = resp["choices"][0]["message"].get("content") or ""
    if isinstance(content, list):  # some providers return a list of chunks
        parts = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict) and chunk.get("type") in (None, "text") and chunk.get("text"):
                parts.append(chunk["text"])
        content = "".join(parts)
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content or "(The model returned an empty reply.)"


GREETING = "Hi! How can I help you plan your trip today?"


def chatbot_page(hf_token):
    st.header("🤖 Travel ChatBot")
    if not hf_token:
        st.warning("Please enter your Hugging Face API token in the sidebar to continue.")
        return

    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"actor": "ai", "payload": GREETING}]

    for msg in st.session_state["messages"]:
        st.chat_message(msg["actor"]).write(msg["payload"])

    query_text = st.chat_input("Ask about hotels, restaurants, or attractions...")
    if not query_text:
        return

    st.session_state["messages"].append({"actor": "user", "payload": query_text})
    st.chat_message("user").write(query_text)

    system_prompt = (
        "You are a helpful travel assistant that provides answers related to travel planning. "
        "You help users with hotel recommendations, restaurant suggestions, tourist attractions, "
        "and general travel information. "
        "Do not give any extra information or context not related to travel. "
        "Only focus on travel-related queries."
    )
    context = st.session_state.get("places_context")
    if context:
        system_prompt += (
            "\n\nReal places found near the user's destination (prefer these when recommending):\n" + context
        )

    messages = [{"role": "system", "content": system_prompt}]
    # Skip the UI-only greeting (index 0) so roles alternate user/assistant,
    # and keep only the most recent turns to bound the prompt size.
    for msg in st.session_state["messages"][1:][-12:]:
        messages.append({
            "role": "user" if msg["actor"] == "user" else "assistant",
            "content": msg["payload"],
        })

    with st.spinner("Thinking..."):
        response = hf_query(messages, hf_token)

    if response is None:
        # Remove the unanswered question so the history stays user/assistant alternating
        st.session_state["messages"].pop()
        return

    try:
        reply = extract_reply(response)
    except (KeyError, IndexError, TypeError):
        st.error("Unexpected response format from the model:")
        st.json(response)
        st.session_state["messages"].pop()
        return

    st.session_state["messages"].append({"actor": "ai", "payload": reply})
    st.chat_message("ai").write(reply)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Travel Recommendation App", page_icon="🌏", layout="wide")
    st.sidebar.title("Travel Recommendation App Demo")

    method = st.sidebar.radio(" ", ["Search 🔎", "ChatBot 🤖", "Database 📑"], key="method_app")

    if method == "ChatBot 🤖":
        hf_token = st.sidebar.text_input(
            "Enter Hugging Face API token:", type="password", value=os.getenv("HF_TOKEN", "")
        )
        if st.sidebar.button("Clear chat"):
            st.session_state.pop("messages", None)
        chatbot_page(hf_token)
        return

    st.sidebar.write("Please fill in the fields below.")
    destination = st.sidebar.text_input("Destination:", key="destination_app").strip()
    radius = st.sidebar.number_input(
        "Search Radius in meter:", value=3000, min_value=500, max_value=50000, step=100, key="radius_app"
    )
    limit = st.sidebar.number_input(
        "Max results per category:", value=15, min_value=5, max_value=50, step=5, key="limit_app"
    )

    if method == "Search 🔎":
        search_page(destination, radius, limit)
    else:
        database_page(destination, radius, limit)


if __name__ == "__main__":
    main()