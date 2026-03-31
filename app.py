from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["PREFERRED_URL_SCHEME"] = "https"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = True

VIDSRC_BASE_URL = "https://vidsrc.icu"
IMDB_SUGGEST_BASE_URL = "https://v2.sg.media-imdb.com/suggestion"
REQUEST_TIMEOUT = 12
MAX_RESULTS = 18
HOME_RAIL_LIMIT = 12
CATALOG_CACHE_PATH = Path(__file__).resolve().parent / "catalog_cache.json"
TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_BACKDROP_BASE_URL = "https://image.tmdb.org/t/p/w1280"


@dataclass
class SearchResult:
    imdb_id: str
    title: str
    media_type: str
    year: str
    subtitle: str
    poster_url: str


def normalize_media_type(raw_type: str) -> str:
    lowered = (raw_type or "").lower()
    if "tv" in lowered or "series" in lowered:
        return "tv"
    return "movie"


def load_catalog_entries() -> dict[str, dict]:
    if not CATALOG_CACHE_PATH.exists():
        return {}

    try:
        payload = json.loads(CATALOG_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    entries = payload.get("entries", {})
    return entries if isinstance(entries, dict) else {}


def tmdb_image_url(path: str, *, backdrop: bool = False) -> str:
    if not path:
        return ""

    base_url = TMDB_BACKDROP_BASE_URL if backdrop else TMDB_POSTER_BASE_URL
    return f"{base_url}{path}"


def extract_year(payload: dict) -> str:
    date_value = (
        payload.get("release_date")
        or payload.get("first_air_date")
        or payload.get("year")
        or ""
    )
    return str(date_value).split("-", 1)[0] if date_value else ""


def summarize_genres(payload: dict) -> str:
    genres = payload.get("genres")
    if isinstance(genres, list) and genres:
        names = [genre.get("name") for genre in genres if isinstance(genre, dict) and genre.get("name")]
        if names:
            return " / ".join(names[:2])

    genre_names = payload.get("genre_names")
    if isinstance(genre_names, list) and genre_names:
        return " / ".join(str(name) for name in genre_names[:2] if name)

    return ""


def format_meta(media_type: str, year: str) -> str:
    parts = ["TV Show" if media_type == "tv" else "Movie"]
    if year:
        parts.append(year)
    return " • ".join(parts)


def format_rating(payload: dict) -> str:
    value = payload.get("vote_average")
    if value in (None, ""):
        return ""

    try:
        return f"{float(value):.1f}/10"
    except (TypeError, ValueError):
        return ""


def extract_cast_names(payload: dict, limit: int = 6) -> list[str]:
    cast_block = payload.get("credits") or payload.get("aggregate_credits") or {}
    cast_items = cast_block.get("cast", []) if isinstance(cast_block, dict) else []
    names: list[str] = []

    for member in cast_items:
        if not isinstance(member, dict):
            continue
        name = str(member.get("name", "")).strip()
        if not name or name in names:
            continue
        names.append(name)
        if len(names) >= limit:
            break

    return names


def lookup_cached_match(entries: dict[str, dict], imdb_id: str, media_type: str) -> dict:
    payload = entries.get(f"find:{imdb_id}", {}).get("data", {})
    bucket = "tv_results" if media_type == "tv" else "movie_results"
    matches = payload.get(bucket, []) if isinstance(payload, dict) else []
    return matches[0] if matches else {}


def lookup_cached_details(entries: dict[str, dict], media_type: str, tmdb_id: int | str | None) -> dict:
    if tmdb_id is None:
        return {}
    return entries.get(f"details:{media_type}:{tmdb_id}", {}).get("data", {})


def lookup_details_for_imdb(entries: dict[str, dict], imdb_id: str, media_type: str) -> dict:
    match = lookup_cached_match(entries, imdb_id, media_type)
    if not match:
        for key, payload in entries.items():
            if not key.startswith(f"details:{media_type}:"):
                continue
            details = payload.get("data", {}) if isinstance(payload, dict) else {}
            if not isinstance(details, dict):
                continue
            external_ids = details.get("external_ids", {})
            cached_imdb_id = details.get("imdb_id") or (
                external_ids.get("imdb_id") if isinstance(external_ids, dict) else None
            )
            if cached_imdb_id == imdb_id:
                return details
        return {}
    return lookup_cached_details(entries, media_type, match.get("id"))


def dedupe_cards(cards: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []

    for card in cards:
        imdb_id = str(card.get("imdb_id", "")).strip()
        if not imdb_id or imdb_id in seen:
            continue
        seen.add(imdb_id)
        deduped.append(card)

    return deduped


def build_catalog_card(
    entries: dict[str, dict],
    item: dict,
    *,
    fallback_media_type: str,
    detail_text: str = "",
    watch_label: str = "Play",
) -> dict | None:
    media_type = normalize_media_type(item.get("media_type") or fallback_media_type)
    details = lookup_cached_details(entries, media_type, item.get("id"))
    external_ids = details.get("external_ids", {}) if isinstance(details, dict) else {}
    imdb_id = details.get("imdb_id") or external_ids.get("imdb_id")
    if not imdb_id:
        return None

    title = (
        details.get("title")
        or details.get("name")
        or item.get("title")
        or item.get("name")
        or "Untitled"
    )
    year = extract_year(details) or extract_year(item)
    poster_url = tmdb_image_url(details.get("poster_path") or item.get("poster_path") or "")
    backdrop_url = tmdb_image_url(
        details.get("backdrop_path") or item.get("backdrop_path") or "",
        backdrop=True,
    )
    genre_text = summarize_genres(details) or summarize_genres(item)
    overview = details.get("overview") or item.get("overview") or ""

    return {
        "imdb_id": imdb_id,
        "title": title,
        "media_type": media_type,
        "year": year,
        "poster_url": poster_url,
        "backdrop_url": backdrop_url,
        "overview": overview,
        "meta": format_meta(media_type, year),
        "detail": detail_text or genre_text or "Ready to play",
        "watch_url": build_watch_url(
            imdb_id,
            media_type,
            title,
            year,
            1,
            1,
            poster_url,
        ),
        "watch_label": watch_label,
        "season": 1,
        "episode": 1,
    }


def build_trending_cards(
    entries: dict[str, dict],
    media_type: str,
    *,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    exclude = exclude_ids or set()
    payload = entries.get(f"trending:{media_type}", {}).get("data", {})
    results = payload.get("results", []) if isinstance(payload, dict) else []

    cards: list[dict] = []
    for item in results:
        card = build_catalog_card(
            entries,
            item,
            fallback_media_type=media_type,
            detail_text="Trending now",
        )
        if not card or card["imdb_id"] in exclude:
            continue
        cards.append(card)
        if len(cards) >= HOME_RAIL_LIMIT:
            break

    return dedupe_cards(cards)


def build_genre_rows(entries: dict[str, dict]) -> list[dict]:
    preferred_genres = [
        ("Drama Picks", {"drama"}),
        ("Comedy Picks", {"comedy"}),
        ("Action Picks", {"action", "action & adventure"}),
        ("Sci-Fi Picks", {"science fiction", "sci-fi & fantasy"}),
    ]

    buckets: dict[str, list[dict]] = {title: [] for title, _ in preferred_genres}
    seen_by_bucket: dict[str, set[str]] = {title: set() for title, _ in preferred_genres}

    for key, payload in entries.items():
        if not key.startswith("details:"):
            continue

        parts = key.split(":")
        if len(parts) < 3:
            continue

        media_type = normalize_media_type(parts[1])
        details = payload.get("data", {}) if isinstance(payload, dict) else {}
        if not isinstance(details, dict):
            continue

        genres = {
            str(genre.get("name", "")).strip().lower()
            for genre in details.get("genres", [])
            if isinstance(genre, dict) and genre.get("name")
        }
        if not genres:
            continue

        card = build_catalog_card(
            entries,
            details,
            fallback_media_type=media_type,
            detail_text=summarize_genres(details) or "Genre pick",
        )
        if not card:
            continue

        for title, targets in preferred_genres:
            if not genres.intersection(targets):
                continue
            if card["imdb_id"] in seen_by_bucket[title]:
                continue
            buckets[title].append(card)
            seen_by_bucket[title].add(card["imdb_id"])

    rows: list[dict] = []
    for title, _targets in preferred_genres:
        cards = buckets[title][:HOME_RAIL_LIMIT]
        if len(cards) >= 4:
            rows.append(
                {
                    "title": title,
                    "subtitle": "A tighter row based on genre.",
                    "cards": cards,
                }
            )
    return rows


def build_hero_card(
    trending_movies: list[dict],
    trending_tv: list[dict],
) -> dict | None:
    fallback_card = (trending_tv or trending_movies or [None])[0]
    if fallback_card:
        hero_card = dict(fallback_card)
        hero_card["eyebrow"] = "Trending Now"
        hero_card["summary"] = hero_card["overview"] or "Popular picks ready to jump into."
        return hero_card

    return None


def search_result_to_card(item: SearchResult, season: int, episode: int) -> dict:
    detail = item.subtitle or (
        f"Starts at Season {season} Episode {episode}"
        if item.media_type == "tv"
        else "Playable now"
    )
    return {
        "imdb_id": item.imdb_id,
        "title": item.title,
        "media_type": item.media_type,
        "year": item.year,
        "poster_url": item.poster_url,
        "backdrop_url": "",
        "overview": "",
        "meta": format_meta(item.media_type, item.year),
        "detail": detail,
        "watch_url": build_watch_url(
            item.imdb_id,
            item.media_type,
            item.title,
            item.year,
            season,
            episode,
            item.poster_url,
        ),
        "watch_label": "Open Player",
        "season": season,
        "episode": episode,
    }


def search_titles(query: str) -> tuple[list[SearchResult], str | None]:
    cleaned = query.strip()
    if not cleaned:
        return [], None

    first_letter = cleaned[0].lower()
    encoded_query = quote(cleaned)
    url = f"{IMDB_SUGGEST_BASE_URL}/{first_letter}/{encoded_query}.json"

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return [], "Search is unavailable right now. Please try again in a moment."

    items = payload.get("d", [])
    results: list[SearchResult] = []

    for item in items:
        imdb_id = item.get("id")
        if not imdb_id or not imdb_id.startswith("tt"):
            continue

        title = item.get("l") or "Untitled"
        media_type = normalize_media_type(item.get("q", "movie"))
        year = str(item.get("y", ""))
        subtitle_parts = [part for part in [item.get("q"), item.get("s")] if part]
        image = item.get("i") or {}

        results.append(
            SearchResult(
                imdb_id=imdb_id,
                title=title,
                media_type=media_type,
                year=year,
                subtitle=" • ".join(subtitle_parts),
                poster_url=image.get("imageUrl", ""),
            )
        )

        if len(results) >= MAX_RESULTS:
            break

    return results, None


def build_embed_url(
    imdb_id: str,
    media_type: str,
    season: int | None = None,
    episode: int | None = None,
) -> str:
    normalized_type = "tv" if media_type == "tv" else "movie"

    if normalized_type == "tv":
        if season and episode:
            return f"{VIDSRC_BASE_URL}/embed/tv/{imdb_id}/{season}/{episode}"
        return f"{VIDSRC_BASE_URL}/embed/tv/{imdb_id}"

    return f"{VIDSRC_BASE_URL}/embed/movie/{imdb_id}"


def build_watch_url(
    imdb_id: str,
    media_type: str,
    title: str,
    year: str = "",
    season: int = 1,
    episode: int = 1,
    poster_url: str = "",
) -> str:
    return url_for(
        "watch",
        media_type=media_type,
        imdb_id=imdb_id,
        title=title,
        year=year,
        season=season,
        episode=episode,
        poster_url=poster_url,
    )


@app.route("/")
def index():
    catalog_entries = load_catalog_entries()

    query = request.args.get("q", "").strip()
    season_raw = request.args.get("season", "1").strip() or "1"
    episode_raw = request.args.get("episode", "1").strip() or "1"
    result_tab = request.args.get("tab", "movies").strip() or "movies"

    season = int(season_raw) if season_raw.isdigit() else 1
    episode = int(episode_raw) if episode_raw.isdigit() else 1

    results: list[SearchResult] = []
    error: str | None = None
    if query:
        results, error = search_titles(query)

    trending_movie_cards = build_trending_cards(catalog_entries, "movie")
    trending_tv_cards = build_trending_cards(catalog_entries, "tv")

    discover_rows: list[dict] = []

    if trending_movie_cards:
        discover_rows.append(
            {
                "title": "Trending Movies",
                "subtitle": "Popular movie picks from the local catalog cache.",
                "cards": trending_movie_cards,
            }
        )

    discover_rows.extend(build_genre_rows(catalog_entries))

    hero_card = build_hero_card(trending_movie_cards, trending_tv_cards)

    movie_results = [search_result_to_card(item, season, episode) for item in results if item.media_type == "movie"]
    tv_results = [search_result_to_card(item, season, episode) for item in results if item.media_type == "tv"]
    current_return_url = (
        url_for("index", q=query, season=season, episode=episode, tab=result_tab)
        if query
        else url_for("index")
    )

    return render_template(
        "index.html",
        query=query,
        movie_results=movie_results,
        tv_results=tv_results,
        saved_items=[],
        saved_movies=[],
        saved_shows=[],
        saved_ids=set(),
        error=error,
        season=season,
        episode=episode,
        result_tab=result_tab,
        discover_rows=discover_rows,
        trending_tv_cards=trending_tv_cards,
        hero_card=hero_card,
        continue_watching_cards=[],
        saved_show_cards=[],
        saved_movie_cards=[],
        current_return_url=current_return_url,
    )


@app.route("/watch/<media_type>/<imdb_id>")
def watch(media_type: str, imdb_id: str):
    normalized_media_type = "tv" if media_type == "tv" else "movie"
    catalog_entries = load_catalog_entries()
    details = lookup_details_for_imdb(catalog_entries, imdb_id, normalized_media_type)

    season_value = request.args.get("season", "1").strip() or "1"
    episode_value = request.args.get("episode", "1").strip() or "1"
    title = request.args.get("title", "Now Playing").strip() or "Now Playing"
    year = request.args.get("year", "").strip()
    poster_url = request.args.get("poster_url", "").strip()

    season = int(season_value) if season_value.isdigit() else 1
    episode = int(episode_value) if episode_value.isdigit() else 1

    embed_url = build_embed_url(
        imdb_id=imdb_id,
        media_type=normalized_media_type,
        season=season if normalized_media_type == "tv" else None,
        episode=episode if normalized_media_type == "tv" else None,
    )

    detail_title = details.get("title") or details.get("name") or ""
    detail_year = extract_year(details)
    detail_poster_url = tmdb_image_url(details.get("poster_path") or "")
    rating = format_rating(details)
    vote_count = details.get("vote_count")
    overview = details.get("overview") or ""
    cast_names = extract_cast_names(details)
    genre_text = summarize_genres(details)

    title = detail_title or title
    year = detail_year or year
    poster_url = detail_poster_url or poster_url

    return render_template(
        "player.html",
        title=title,
        year=year,
        imdb_id=imdb_id,
        media_type=normalized_media_type,
        season=season,
        episode=episode,
        embed_url=embed_url,
        poster_url=poster_url,
        overview=overview,
        rating=rating,
        vote_count=vote_count,
        cast_names=cast_names,
        genre_text=genre_text,
        return_to=request.referrer or url_for("index"),
    )


@app.route("/info")
def info():
    return render_template("info.html")


@app.after_request
def add_security_headers(response):
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


if __name__ == "__main__":
    debug = os.environ.get("STREAM_FINDER_DEBUG", "1") == "1"
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=debug, host="0.0.0.0", port=port)
