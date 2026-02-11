var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
export const BASEURL = `http://${location.host.split(":")[0]}:5001`;
var MALPages = {};
export function wrap(text, max_width) {
    if (text.length > max_width) {
        return `${text.slice(0, max_width - 3)}...`;
    }
    return text;
}
export function request(method_1, url_1) {
    return __awaiter(this, arguments, void 0, function* (method, url, params = null, body = null) {
        var i = {
            method: method,
            body: null,
            headers: {},
        };
        if (params) {
            url += "?" + new URLSearchParams(params);
        }
        if (body) {
            i.body = JSON.stringify(body);
            i.headers["Content-Type"] = "application/json";
        }
        try {
            const response = yield fetch(url, i);
            if (!response.ok) {
                throw new Error(`Error when requesting ${url}. Error ${response.status}: ${yield response.text()}`);
            }
            return response;
        }
        catch (e) {
            throw new Error(`Error when requesting ${url}. Error ${e}`);
        }
    });
}
export function resolve_mal_page(object) {
    return __awaiter(this, void 0, void 0, function* () {
        var _a, _b;
        const MALPageButton = document.getElementById('mal-page-button');
        if (object.title in MALPages) {
            const url = MALPages[object.title];
            if (url !== null) {
                (_a = window.open(url, '_blank')) === null || _a === void 0 ? void 0 : _a.focus();
            }
            else if (MALPageButton != undefined) {
                MALPageButton.classList = "line-through my-3 border border-white bg-black";
                MALPageButton.onclick = null;
            }
            return;
        }
        const resp = yield request('GET', BASEURL + '/api/get_mal_page', { 'title': object.title, 'other_title': object.other_title });
        const json = yield resp.json();
        const url = json.url;
        MALPages[object.title] = url;
        if (url !== null) {
            (_b = window.open(url, '_blank')) === null || _b === void 0 ? void 0 : _b.focus();
        }
        else if (MALPageButton != undefined) {
            MALPageButton.classList = "line-through my-3 border border-white bg-black";
            MALPageButton.onclick = null;
        }
    });
}
