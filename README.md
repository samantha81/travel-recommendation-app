# Travel Recommender (OpenStreetMap)

A Streamlit web app that finds hotels, restaurants and tourist attractions near any destination using **free OpenStreetMap data**, plus a travel chatbot powered by Hugging Face Inference Providers.

**No Google API key and no credit card required** for the search features.

<!-- Add a screenshot here: ![Search tab](docs/screenshot.png) -->

## Features

- **Search**: enter a destination and radius, pick Hotels, Restaurants or Tourist Attractions, and see them on an interactive map with a list of details (address, phone, website, distance, OpenStreetMap link).
- **Database**: all results in one sortable table, with clickable links and CSV download.
- **ChatBot**: ask travel questions. If you searched a destination first, the chatbot is given the real places found nearby so it can recommend them.
- Results are sorted by distance and cached for one hour to be gentle on the free public servers.

## How it works

| Step | Service | Key needed? |
|---|---|---|
| Destination to coordinates | [Nominatim](https://nominatim.org/) (backup: [Photon](https://photon.komoot.io/)) | No |
| Nearby hotels, restaurants, attractions | [Overpass API](https://overpass-api.de/) (OpenStreetMap), with mirror fallback | No |
| Map display | [folium](https://python-visualization.github.io/folium/) + [streamlit-folium](https://github.com/randyzwitch/streamlit-folium) | No |
| ChatBot | [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers) | Yes, a free HF token |

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py
```

The app opens at http://localhost:8501.

## Configuration

Settings are optional environment variables. Copy `.env.example` to `.env` and fill it in (the `.env` file is git-ignored, so your secrets stay private).

| Variable | Used for | Notes |
|---|---|---|
| `APP_CONTACT` | Identifies your app to OpenStreetMap servers | **Set your real email.** Nominatim's usage policy requires an identifying User-Agent, and requests with the placeholder address may be rejected (HTTP 403). |
| `HF_TOKEN` | ChatBot | Optional. If unset, paste the token into the sidebar instead. |

### Getting a Hugging Face token (ChatBot only)

1. Create a free account at https://huggingface.co.
2. Go to **Settings, then Access Tokens**, and create a token.
3. Make sure it has the **"Make calls to Inference Providers"** permission.
4. Paste it in the ChatBot tab's sidebar, or put it in `.env` as `HF_TOKEN`.

Free usage is limited. If you hit a quota error (HTTP 402 or 429), wait for it to reset or check your usage on Hugging Face.

## Usage

1. Choose **Search** in the sidebar, type a destination (for example `London`), and adjust the radius and the number of results per category.
2. Switch between Hotels, Restaurants and Tourist Attractions.
3. Open **Database** for the full table and CSV export.
4. Open **ChatBot** and ask something like "What should I do in London for two days?" For better answers, run a Search for the same destination first.

## Project structure

```
.
├── app.py              # the whole Streamlit app
├── requirements.txt
├── .env.example        # template for your local .env
├── .gitignore
└── README.md
```

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| 403 from Nominatim | Placeholder or missing `APP_CONTACT`. Set a real email. Also try without a VPN or on another network. The app falls back to Photon automatically. |
| "All Overpass servers failed or are busy" | The free public servers are sometimes overloaded. Wait a minute and refresh. |
| Few or no results | Increase the search radius. OpenStreetMap coverage varies by country and category. |
| ChatBot HTTP 401 or 403 | Token is wrong or lacks the "Make calls to Inference Providers" permission. |
| ChatBot "Model not supported" | Provider catalogs change. The app tries several models in order; edit the `HF_MODELS` list at the top of `app.py` to use another model. |

## Limitations

- OpenStreetMap has **no ratings or reviews**, so results are ranked by distance.
- Data completeness (addresses, websites, phone numbers) depends on volunteer contributors, so many entries show `N/A`.
- The public Nominatim and Overpass servers have usage limits and no uptime guarantee. This app is intended as a demo, not for heavy or commercial traffic. For production, consider self-hosting or a paid provider.
- The chatbot is a general language model and can still make mistakes. Check important details such as opening hours and prices.

## Data attribution

Place data and map tiles are © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the Open Database License (ODbL).

## License

MIT (add a `LICENSE` file when you create the repository).
