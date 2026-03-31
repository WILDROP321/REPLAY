(function () {
    const STORAGE_KEY = "stream-finder-library-v1";

    function readLibrary() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            const parsed = raw ? JSON.parse(raw) : {};
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (_error) {
            return {};
        }
    }

    function writeLibrary(library) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(library));
    }

    function getCardData(element) {
        return {
            imdb_id: element.dataset.imdbId,
            title: element.dataset.title || "Untitled",
            media_type: element.dataset.mediaType === "tv" ? "tv" : "movie",
            year: element.dataset.year || "",
            poster_url: element.dataset.posterUrl || "",
            season: Number.parseInt(element.dataset.season || "1", 10) || 1,
            episode: Number.parseInt(element.dataset.episode || "1", 10) || 1,
            watch_url: element.dataset.watchUrl || "#",
        };
    }

    function escapeHtml(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function buildWatchUrl(item) {
        const params = new URLSearchParams({
            title: item.title,
            year: item.year || "",
            season: String(item.season || 1),
            episode: String(item.episode || 1),
            poster_url: item.poster_url || "",
        });
        return `/watch/${item.media_type}/${item.imdb_id}?${params.toString()}`;
    }

    function sortLibraryItems(library) {
        return Object.values(library).sort((a, b) => a.title.localeCompare(b.title));
    }

    function upsertItem(item) {
        const library = readLibrary();
        const existing = library[item.imdb_id] || {};
        library[item.imdb_id] = {
            imdb_id: item.imdb_id,
            title: item.title || existing.title || "Untitled",
            media_type: item.media_type || existing.media_type || "movie",
            year: item.year || existing.year || "",
            poster_url: item.poster_url || existing.poster_url || "",
            season: item.media_type === "tv" ? (item.season || existing.season || 1) : 1,
            episode: item.media_type === "tv" ? (item.episode || existing.episode || 1) : 1,
            updated_at: item.updated_at || new Date().toISOString(),
            starred: typeof item.starred === "boolean" ? item.starred : Boolean(existing.starred),
        };
        writeLibrary(library);
        return library;
    }

    function removeItem(imdbId) {
        const library = readLibrary();
        delete library[imdbId];
        writeLibrary(library);
        return library;
    }

    function toggleStar(item) {
        const library = readLibrary();
        const existing = library[item.imdb_id];

        if (existing && existing.starred) {
            existing.starred = false;
            if (existing.media_type !== "tv" || !existing.updated_at) {
                delete library[item.imdb_id];
            } else {
                library[item.imdb_id] = existing;
            }
            writeLibrary(library);
            return library;
        }

        return upsertItem({ ...item, starred: true });
    }

    function renderLibraryCard(item) {
        const detail = item.media_type === "tv"
            ? `Resume at Season ${item.season} Episode ${item.episode}`
            : "Ready to continue";
        const watchLabel = item.media_type === "tv" ? "Resume" : "Play";
        const actionLabel = item.starred ? "Unstar" : "Remove";
        const poster = item.poster_url
            ? `<img src="${escapeHtml(item.poster_url)}" alt="${escapeHtml(item.title)} poster" class="card-poster">`
            : `<div class="card-poster placeholder">${escapeHtml(item.title)}</div>`;

        return `
            <article class="stream-card media-card library-media-card">
                <a class="card-poster-link" href="${escapeHtml(buildWatchUrl(item))}">
                    <div class="card-poster-frame">${poster}</div>
                </a>
                <div class="card-body">
                    <p class="card-meta">${escapeHtml(item.media_type === "tv" ? "TV Show" : "Movie")}${item.year ? ` • ${escapeHtml(item.year)}` : ""}</p>
                    <h3 class="card-title">${escapeHtml(item.title)}</h3>
                    <p class="card-detail">${escapeHtml(detail)}</p>
                    <div class="card-actions">
                        <a class="card-button" href="${escapeHtml(buildWatchUrl(item))}">${watchLabel}</a>
                        <button type="button" class="card-button secondary js-saved-toggle" data-imdb-id="${escapeHtml(item.imdb_id)}">${actionLabel}</button>
                    </div>
                </div>
            </article>
        `;
    }

    function renderTrendingCard(card) {
        const poster = card.poster_url
            ? `<img src="${escapeHtml(card.poster_url)}" alt="${escapeHtml(card.title)} poster" class="card-poster">`
            : `<div class="card-poster placeholder">${escapeHtml(card.title)}</div>`;

        return `
            <article
                class="stream-card media-card"
                data-imdb-id="${escapeHtml(card.imdb_id)}"
                data-title="${escapeHtml(card.title)}"
                data-media-type="${escapeHtml(card.media_type)}"
                data-year="${escapeHtml(card.year || "")}"
                data-poster-url="${escapeHtml(card.poster_url || "")}"
                data-season="${escapeHtml(String(card.season || 1))}"
                data-episode="${escapeHtml(String(card.episode || 1))}"
                data-watch-url="${escapeHtml(card.watch_url)}"
            >
                <a class="card-poster-link" href="${escapeHtml(card.watch_url)}">
                    <div class="card-poster-frame">${poster}</div>
                </a>
                <div class="card-body">
                    <p class="card-meta">${escapeHtml(card.meta || "")}</p>
                    <h3 class="card-title">${escapeHtml(card.title)}</h3>
                    <p class="card-detail">${escapeHtml(card.detail || "Trending now")}</p>
                    <div class="card-actions">
                        <a class="card-button" href="${escapeHtml(card.watch_url)}">${escapeHtml(card.watch_label || "Play")}</a>
                        <button type="button" class="card-button secondary js-library-toggle">Star</button>
                    </div>
                </div>
            </article>
        `;
    }

    function updateStats(library) {
        const items = Object.values(library).filter((item) => item.starred);
        const shows = items.filter((item) => item.media_type === "tv").length;
        const movies = items.filter((item) => item.media_type === "movie").length;

        const savedCount = document.getElementById("saved-count-pill");
        const showCount = document.getElementById("show-count-pill");
        const movieCount = document.getElementById("movie-count-pill");

        if (savedCount) savedCount.textContent = `${items.length} saved`;
        if (showCount) showCount.textContent = `${shows} shows`;
        if (movieCount) movieCount.textContent = `${movies} movies`;
    }

    function bindSavedCardButtons() {
        document.querySelectorAll(".js-saved-toggle").forEach((button) => {
            button.onclick = function () {
                const library = readLibrary();
                const item = library[button.dataset.imdbId];
                if (!item) return;
                if (item.starred) {
                    toggleStar(item);
                } else {
                    removeItem(item.imdb_id);
                }
                refreshHomeLibrary();
                refreshSearchButtons();
                refreshPlayerStarButton();
            };
        });
    }

    function setSection(containerId, emptyId, panelId, items) {
        const container = document.getElementById(containerId);
        const empty = document.getElementById(emptyId);
        const panel = document.getElementById(panelId);
        if (!container || !empty || !panel) return false;

        container.innerHTML = items.map(renderLibraryCard).join("");
        empty.hidden = items.length > 0;
        panel.hidden = items.length === 0;
        return items.length > 0;
    }

    function refreshHomeLibrary() {
        const library = readLibrary();
        const items = sortLibraryItems(library);
        const continueWatching = items
            .filter((item) => item.updated_at)
            .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))
            .slice(0, 6);
        const shows = items.filter((item) => item.media_type === "tv" && item.starred);
        const movies = items.filter((item) => item.media_type === "movie" && item.starred);

        const hasContinue = setSection("continue-watching-grid", "continue-empty", "continue-panel", continueWatching);
        const hasShows = setSection("saved-shows-grid", "shows-empty", "shows-panel", shows);
        const hasMovies = setSection("saved-movies-grid", "movies-empty", "movies-panel", movies);
        const libraryColumn = document.getElementById("library-column");
        if (libraryColumn) {
            libraryColumn.hidden = !(hasContinue || hasShows || hasMovies);
        }
        updateStats(library);
        bindSavedCardButtons();
    }

    function refreshSearchButtons() {
        const library = readLibrary();
        document.querySelectorAll(".media-card").forEach((card) => {
            const button = card.querySelector(".js-library-toggle");
            const link = card.querySelector(".card-poster-link, .card-button");
            const savedItem = library[card.dataset.imdbId];
            if (!button) return;
            button.textContent = savedItem && savedItem.starred ? "Unstar" : "Star";

            if (savedItem && link) {
                const savedUrl = buildWatchUrl(savedItem);
                card.dataset.watchUrl = savedUrl;
                card.querySelectorAll("a[href]").forEach((anchor) => {
                    if (anchor.classList.contains("card-poster-link") || anchor.classList.contains("card-button")) {
                        anchor.href = savedUrl;
                    }
                });
            }
        });
    }

    function setupSearchCards() {
        document.querySelectorAll(".media-card").forEach((card) => {
            const button = card.querySelector(".js-library-toggle");
            if (!button || button.dataset.bound === "1") return;
            button.dataset.bound = "1";
            button.addEventListener("click", function () {
                const data = getCardData(card);
                toggleStar(data);
                refreshHomeLibrary();
                refreshSearchButtons();
                refreshPlayerStarButton();
            });
        });
        refreshSearchButtons();
    }

    function setupControlledCarousels() {
        document.querySelectorAll(".js-carousel-shell").forEach((shell) => {
            const rail = shell.querySelector(".js-card-rail");
            const block = shell.closest(".rail-block, .library-panel");
            const prev = block ? block.querySelector(".js-carousel-prev") : null;
            const next = block ? block.querySelector(".js-carousel-next") : null;
            if (!rail || !prev || !next || rail.dataset.carouselReady === "1") return;

            rail.dataset.carouselReady = "1";

            const scrollByPage = (direction) => {
                const distance = Math.max(shell.clientWidth - 64, 220) * direction;
                shell.scrollBy({ left: distance, behavior: "smooth" });
            };

            prev.addEventListener("click", function () {
                scrollByPage(-1);
            });

            next.addEventListener("click", function () {
                scrollByPage(1);
            });
        });
    }

    function refreshPlayerStarButton() {
        const body = document.body;
        const button = document.querySelector(".js-player-star");
        if (!body || !button || body.dataset.page !== "player") return;

        const library = readLibrary();
        const imdbId = body.dataset.imdbId;
        button.textContent = library[imdbId] && library[imdbId].starred ? "Unstar" : "Star";
    }

    function setupPlayerPage() {
        const body = document.body;
        if (!body || body.dataset.page !== "player") return;

        const playerData = {
            imdb_id: body.dataset.imdbId,
            title: body.dataset.title || "Untitled",
            media_type: body.dataset.mediaType === "tv" ? "tv" : "movie",
            year: body.dataset.year || "",
            poster_url: body.dataset.posterUrl || "",
            season: Number.parseInt(body.dataset.season || "1", 10) || 1,
            episode: Number.parseInt(body.dataset.episode || "1", 10) || 1,
        };

        const starButton = document.querySelector(".js-player-star");
        if (starButton) {
            starButton.addEventListener("click", function () {
                toggleStar(playerData);
                refreshPlayerStarButton();
                refreshHomeLibrary();
                refreshSearchButtons();
            });
        }

        const episodeForm = document.querySelector(".js-episode-form");
        if (episodeForm) {
            episodeForm.addEventListener("submit", function () {
                const seasonInput = episodeForm.querySelector('input[name="season"]');
                const episodeInput = episodeForm.querySelector('input[name="episode"]');
                playerData.season = Number.parseInt(seasonInput.value || "1", 10) || 1;
                playerData.episode = Number.parseInt(episodeInput.value || "1", 10) || 1;
                upsertItem(playerData);
            });
        }

        upsertItem(playerData);

        refreshPlayerStarButton();
    }

    setupControlledCarousels();
    setupSearchCards();
    setupPlayerPage();
    refreshHomeLibrary();
})();
