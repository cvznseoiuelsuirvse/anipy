var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var _a;
import { request, BASEURL, resolve_mal_page } from "./util.js";
var modal_active = false;
function watchlist(object, action) {
    return __awaiter(this, void 0, void 0, function* () {
        if (action == "add") { }
        else { }
    });
}
;
function highlight(object) {
    return __awaiter(this, void 0, void 0, function* () {
        object['highlighted'] = !object['highlighted'];
        const resp = yield request("POST", BASEURL + "/api/datalist/modify", null, {
            "filter": "watchlist",
            "action": "update",
            "object": object,
        });
        if (resp.ok) {
            const box = document.getElementById(object.id);
            if (box) {
                box.className = object.highlighted ? "relative border-white border p-3 h-full" : "relative border-zinc-700 group-hover:border-white border p-3 h-full";
            }
        }
    });
}
export function closeSearchbar() {
    const searchbar = document.getElementById("searchbar");
    if (searchbar != undefined)
        searchbar.style.display = 'none';
}
function showSearchbar() {
    if (modal_active)
        return;
    modal_active = true;
    document.body.style.overflow = 'hidden';
    const modal = document.getElementById("modal");
    const searchbar = document.getElementById("searchbar");
    const searchbar_input = document.getElementById("searchbar-input");
    if (modal != undefined)
        modal.style.display = 'block';
    if (searchbar != undefined)
        searchbar.style.display = 'block';
    searchbar_input === null || searchbar_input === void 0 ? void 0 : searchbar_input.focus();
}
export function closeInfoPopup() {
    const popup = document.getElementById("info-popup");
    const content = document.getElementById("info-popup-content");
    if (popup != undefined)
        popup.style.display = 'none';
    if (content != undefined)
        content.innerHTML = '';
}
function showInfoPopup(object) {
    console.log(object);
    if (modal_active)
        return;
    modal_active = true;
    const modal = document.getElementById("modal");
    const popup = document.getElementById("info-popup");
    const content = document.getElementById("info-popup-content");
    document.body.style.overflow = 'hidden';
    if (modal != undefined)
        modal.style.display = 'block';
    if (popup != undefined)
        popup.style.display = 'block';
    const popup_title = document.createElement('div');
    popup_title.classList = 'absolute -top-3 bg-black px-2 left-5 max-w-[96%] truncate';
    popup_title.textContent = `${object.title} (${object.other_title})`;
    popup_title.title = object.title;
    const content_box = document.createElement("div");
    content_box.classList = "grid grid-cols-3 grid-rows-5 gap-6 h-full";
    const poster_box = document.createElement("div");
    poster_box.classList = "row-span-5";
    const poster = document.createElement("img");
    poster.classList = 'w-full h-full object-contain';
    poster.src = object.poster;
    poster_box.appendChild(poster);
    const description_box = document.createElement("div");
    description_box.classList = "relative border-zinc-500 border p-4 col-span-2 row-span-2 col-start-2";
    const description_box_title = document.createElement("div");
    description_box_title.classList = "absolute -top-3 bg-black px-2 left-5";
    description_box_title.textContent = "description";
    const description_box_content = document.createElement("div");
    description_box_content.classList = "overflow-auto h-full";
    description_box_content.textContent = object.description;
    description_box.appendChild(description_box_title);
    description_box.appendChild(description_box_content);
    const info_box = document.createElement("div");
    info_box.classList = "relative border-zinc-500 border p-4 col-span-2 row-span-2 col-start-2 row-start-3 grid grid-cols-3 grid-rows-1 h-full auto-rows-fr";
    const create_info_cell = (header, content) => {
        const cell = document.createElement("div");
        cell.classList = "flex flex-col justify-center items-center";
        const header_elem = document.createElement("span");
        header_elem.classList = "text-zinc-500";
        header_elem.textContent = header;
        const content_elem = document.createElement("span");
        content_elem.textContent = content;
        cell.appendChild(header_elem);
        cell.appendChild(content_elem);
        return cell;
    };
    const info_box_title = document.createElement("div");
    info_box_title.classList = "absolute -top-3 bg-black px-2 left-5";
    info_box_title.textContent = "info";
    info_box.appendChild(info_box_title);
    info_box.appendChild(create_info_cell("genres", typeof object.genres == 'string' ? object.genres.split(",").join(' - ') : object.genres.join(' - ')));
    info_box.appendChild(create_info_cell("year", object.year));
    info_box.appendChild(create_info_cell("episodes", object.episode_count));
    info_box.appendChild(create_info_cell("type", object.type));
    if (object.finished_at > 1) {
        const date = new Date(object.finished_at * 1000);
        const options = {
            year: "numeric",
            month: "long",
            day: "numeric",
        };
        info_box.appendChild(create_info_cell("done watching", date.toLocaleDateString("en-US", options)));
    }
    else {
        info_box.appendChild(create_info_cell("airing", object.airing_status));
    }
    info_box.appendChild(create_info_cell("duration", object.episode_duration));
    const button_box = document.createElement("div");
    button_box.classList = "col-span-2 col-start-2 row-start-5 grid grid-cols-3 gap-9";
    const create_button = () => {
        const button = document.createElement("button");
        button.classList = "my-4 border border-white bg-black hover:border-none hover:bg-white hover:text-black";
        return button;
    };
    const HiAnimeButton = create_button();
    HiAnimeButton.textContent = 'HiAnime';
    HiAnimeButton.onclick = () => { var _a; (_a = window.open(object.url, '_blank')) === null || _a === void 0 ? void 0 : _a.focus(); };
    const MALButton = create_button();
    MALButton.textContent = 'MAL';
    MALButton.onclick = () => { var _a; (_a = window.open(`https://myanimelist.net/anime.php?q=${object.title}&cat=anime`, '_blank')) === null || _a === void 0 ? void 0 : _a.focus(); };
    const MALPageButton = create_button();
    MALPageButton.textContent = 'MAL Page';
    MALPageButton.onclick = () => __awaiter(this, void 0, void 0, function* () { resolve_mal_page(object); });
    MALPageButton.id = 'mal-page-button';
    const buttons = [HiAnimeButton, MALButton, MALPageButton];
    for (var b of buttons) {
        button_box.appendChild(b);
    }
    content_box.appendChild(poster_box);
    content_box.appendChild(description_box);
    content_box.appendChild(info_box);
    content_box.appendChild(button_box);
    content === null || content === void 0 ? void 0 : content.appendChild(popup_title);
    content === null || content === void 0 ? void 0 : content.appendChild(content_box);
}
export function loadWatchlist() {
    return __awaiter(this, void 0, void 0, function* () {
        const data_grid = document.getElementById("data-grid");
        const response = yield request("GET", BASEURL + "/api/datalist", { "filter": "watchlist" });
        var json = yield response.json();
        json = json.reverse();
        const title = document.getElementById("title");
        if (title != undefined)
            title.textContent = title.textContent + ` (${json.length})`;
        for (let object of json) {
            const group_box = document.createElement("div");
            group_box.classList = "group";
            group_box.onclick = (e) => __awaiter(this, void 0, void 0, function* () {
                if (e.shiftKey) {
                    highlight(object);
                }
                else {
                    showInfoPopup(object);
                }
            });
            const box = document.createElement("div");
            box.className = object.highlighted ? "relative border-white border p-3 h-full" : "relative border-zinc-700 group-hover:border-white border p-3 h-full";
            box.id = object.id;
            const box_title = document.createElement("div");
            box_title.classList = "absolute -top-3 bg-black px-2 left-5 z-10";
            if (object.continue_from > 1) {
                box_title.textContent = `${object.continue_from}/${object.episode_count}`;
            }
            const poster = document.createElement("img");
            poster.src = object.poster;
            poster.loading = "lazy";
            poster.classList = "grayscale brightness-50 group-hover:grayscale-0 group-hover:brightness-100";
            const title = document.createElement("div");
            title.classList = "text-sm mt-2";
            title.textContent = object.title;
            box.appendChild(box_title);
            box.appendChild(poster);
            box.appendChild(title);
            group_box.appendChild(box);
            data_grid === null || data_grid === void 0 ? void 0 : data_grid.appendChild(group_box);
        }
    });
}
export function loadCompleted() {
    return __awaiter(this, void 0, void 0, function* () {
        const data_grid = document.getElementById("data-grid");
        const response = yield request("GET", BASEURL + "/api/datalist", { "filter": "completed" });
        var json = (yield response.json()).reverse();
        const title = document.getElementById("title");
        if (title != undefined)
            title.textContent = title.textContent + ` (${json.length})`;
        for (let object of json) {
            const group_box = document.createElement("div");
            group_box.classList = "group";
            group_box.onclick = () => { showInfoPopup(object); };
            const box = document.createElement("div");
            if (object.id == "school-days-8757") {
                box.className = "relative border-white border animation-pulse p-3 h-full";
            }
            else {
                box.className = "relative border-zinc-700 group-hover:border-white border p-3 h-full";
            }
            box.id = object.id;
            const box_title = document.createElement("div");
            box_title.classList = "absolute -top-3 bg-black px-2 left-5 z-10";
            const poster = document.createElement("img");
            poster.src = object.poster;
            poster.loading = "lazy";
            if (object.id != "school-days-8757") {
                poster.classList = "grayscale brightness-50 group-hover:grayscale-0 group-hover:brightness-100";
            }
            const title = document.createElement("div");
            title.classList = "text-sm mt-2";
            title.textContent = object.title;
            box.appendChild(box_title);
            box.appendChild(poster);
            box.appendChild(title);
            group_box.appendChild(box);
            data_grid === null || data_grid === void 0 ? void 0 : data_grid.appendChild(group_box);
        }
    });
}
export function loadSearchResults() {
    return __awaiter(this, void 0, void 0, function* () {
        const data_grid = document.getElementById("data-grid");
        const url = new URL(window.location.href);
        const query = url.searchParams.get('q');
        const version = url.searchParams.get('version');
        const response = yield request("GET", BASEURL + "/api/search", { query: query, version: version ? version : 'both' });
        var json = yield response.json();
        console.log(json);
        const title = document.getElementById("title");
        if (title != undefined)
            title.textContent = title.textContent + ` (${json.length})`;
        for (let object of json) {
            const group_box = document.createElement("div");
            group_box.classList = "group";
            group_box.onclick = (e) => __awaiter(this, void 0, void 0, function* () {
                const _response = yield request("GET", BASEURL + "/api/get_anime_info", { id: object.id, version: version ? version : 'sub' });
                const _object = yield _response.json();
                showInfoPopup(_object);
            });
            const box = document.createElement("div");
            box.className = "relative border-zinc-700 group-hover:border-white border p-3 h-full";
            box.id = object.id;
            const box_title = document.createElement("div");
            box_title.classList = "absolute -top-3 bg-black px-2 left-5 z-10";
            const poster = document.createElement("img");
            poster.src = object.poster;
            poster.loading = "lazy";
            poster.classList = "grayscale brightness-50 group-hover:grayscale-0 group-hover:brightness-100";
            const title = document.createElement("div");
            title.classList = "text-sm mt-2";
            title.textContent = object.title;
            box.appendChild(box_title);
            box.appendChild(poster);
            box.appendChild(title);
            group_box.appendChild(box);
            data_grid === null || data_grid === void 0 ? void 0 : data_grid.appendChild(group_box);
        }
    });
}
export function closePopups() {
    modal_active = false;
    const modal = document.getElementById("modal");
    document.body.style.overflow = 'auto';
    if (modal != undefined)
        modal.style.display = 'none';
    closeInfoPopup();
    closeSearchbar();
}
document.addEventListener('keydown', (e) => {
    if (e.key == 'Escape') {
        closePopups();
    }
    else if (e.key == 'p') {
        if ((navigator.userAgent.match("Macintosh") && e.metaKey) || !(navigator.userAgent.match('Macintosh')) && e.altKey) {
            e.preventDefault();
            showSearchbar();
        }
    }
});
(_a = document
    .getElementById("searchbar-input")) === null || _a === void 0 ? void 0 : _a.addEventListener("keypress", (e) => __awaiter(void 0, void 0, void 0, function* () {
    if (e.key == "Enter") {
        e.preventDefault();
        const searchbar = document.getElementById("searchbar-input");
        const query = searchbar.value;
        var params = { q: query, version: 'sub' };
        window.location.href = `${BASEURL}/search?` + new URLSearchParams(params);
    }
}));
