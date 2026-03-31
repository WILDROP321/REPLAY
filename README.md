# REPLAY

REPLAY is a Flask media browser that lets users search movies and TV shows, open a web player, and keep a personal library in browser storage. Saved titles, continue-watching progress, and episode resume state are stored locally in each browser instead of on the server.

## Features

- Search movies and TV shows from IMDb suggestions
- Browse curated homepage rails built from a local catalog cache
- Open a player page with metadata such as overview, rating, genres, and cast
- Keep per-browser saved shows, saved movies, and continue-watching history
- Show informational copyright and content-source notice at `/info`

## Stack

- Python
- Flask
- Gunicorn
- Vanilla JavaScript
- CSS

## Local Development

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python app.py
```

4. Open [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Deploying To Render

This repo includes a `render.yaml`, so you can deploy it as a Render Web Service directly from GitHub.

1. Push this project to a GitHub repository.
2. In Render, choose `New +` -> `Blueprint`.
3. Connect the GitHub repo and select this project.
4. Render will read `render.yaml` and create the service automatically.
5. After the first deploy, open the Render URL.

If you prefer manual setup instead of a blueprint:

- Runtime: `Python`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

The app already reads the `PORT` environment variable and binds to `0.0.0.0`, which is required for Render.

## Data And Privacy

- Personal library state is stored in the browser with `localStorage`
- The server does not keep per-user watch history
- `library.json` is excluded from Git and not used for deployed user data
- Flask debug mode is disabled in production through `STREAM_FINDER_DEBUG=0`

## Publishing Safely

Before pushing publicly, keep these rules in place:

- Do not commit `.venv/`
- Do not commit `library.json`
- Do not add API keys, cookies, tokens, or personal credentials to the repo
- Keep deployment secrets in Render environment variables, not in source code

## Disclaimer

This app does not upload or host media files. Content availability is provided by third-party sources. Copyright remains with the respective owners. Rights holders can contact the operator for takedown requests.
