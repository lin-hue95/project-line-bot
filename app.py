from flask import Flask, request, abort
import os
import requests

from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError


app = Flask(__name__)

configuration = Configuration(
    access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
)

handler = WebhookHandler(
    os.getenv("LINE_CHANNEL_SECRET")
)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")


# 電影類型 ID
MOVIE_GENRE_MAP = {
    "喜劇": 35,
    "恐怖": 27,
    "愛情": 10749,
    "動畫": 16,
    "動作": 28,
    "懸疑": 9648,
    "科幻": 878,
    "冒險": 12,
    "劇情": 18,
    "家庭": 10751,
    "犯罪": 80,
    "奇幻": 14
}


# 影集類型 ID
TV_GENRE_MAP = {
    "喜劇": 35,
    "恐怖": 9648,
    "愛情": 18,
    "動畫": 16,
    "動作": 10759,
    "懸疑": 9648,
    "科幻": 10765,
    "冒險": 10759,
    "劇情": 18,
    "家庭": 10751,
    "犯罪": 80,
    "奇幻": 10765
}


# 心情推薦：會同時推薦電影與影集
MOOD_MAP = {
    "想放鬆": ["喜劇", "動畫", "家庭"],
    "想哭": ["劇情", "愛情"],
    "想被療癒": ["動畫", "家庭", "劇情"],
    "想刺激": ["恐怖", "動作"],
    "想燒腦": ["懸疑", "科幻", "犯罪"],
    "想浪漫": ["愛情", "喜劇"],
    "想熱血": ["動作", "冒險"],
}


# 情境推薦：會同時推薦電影與影集
SCENE_MAP = {
    "一個人看": ["懸疑", "劇情", "科幻"],
    "朋友一起看": ["喜劇", "動作", "動畫"],
    "約會看": ["愛情", "喜劇", "動畫"],
    "睡前看": ["動畫", "家庭", "喜劇"],
    "吃飯配片": ["喜劇", "動畫", "冒險"],
    "假日看": ["冒險", "動作", "喜劇"],
}


# 記住使用者上一輪推薦過什麼，讓「換一批」不重複
user_sessions = {}


@app.route("/", methods=["GET"])
def home():
    return "Movie and TV LINE Bot is running."


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id

    reply_text = handle_user_text(user_text, user_id)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )


def handle_user_text(text, user_id):
    if text in ["說明", "功能", "help", "Help", "HELP"]:
        return get_help_text()

    # 熱門推薦
    if text == "熱門電影":
        return get_popular_items(user_id, media_type="movie", reset=True)

    if text == "熱門影集":
        return get_popular_items(user_id, media_type="tv", reset=True)

    if text in ["熱門影視", "熱門推薦"]:
        return get_popular_items(user_id, media_type="all", reset=True)

    # 隨機推薦
    if text in ["隨機推薦", "幫我選", "隨便推薦"]:
        return get_popular_items(user_id, media_type="all", reset=True, title="今晚隨機推薦")

    if text == "隨機電影":
        return get_popular_items(user_id, media_type="movie", reset=True, title="隨機電影推薦")

    if text in ["隨機影集", "隨機劇"]:
        return get_popular_items(user_id, media_type="tv", reset=True, title="隨機影集推薦")

    # 換一批
    if text in ["換一批", "繼續推薦", "再推薦"]:
        return recommend_next_batch(user_id)

    # 查詢電影 / 影集
    if text.startswith("查電影 "):
        keyword = text.replace("查電影 ", "", 1).strip()
        return search_item(keyword, media_type="movie")

    if text.startswith("查影集 "):
        keyword = text.replace("查影集 ", "", 1).strip()
        return search_item(keyword, media_type="tv")

    if text.startswith("查劇 "):
        keyword = text.replace("查劇 ", "", 1).strip()
        return search_item(keyword, media_type="tv")

    # 推薦類型：例如 推薦喜劇、推薦喜劇電影、推薦喜劇影集
    if text.startswith("推薦"):
        content = text.replace("推薦", "", 1).strip()

        if content.endswith("電影"):
            genre = content.replace("電影", "").strip()
            return recommend_by_genre(genre, user_id, media_type="movie", reset=True)

        if content.endswith("影集"):
            genre = content.replace("影集", "").strip()
            return recommend_by_genre(genre, user_id, media_type="tv", reset=True)

        return recommend_by_genre(content, user_id, media_type="all", reset=True)

    # 依心情推薦：電影 + 影集
    if text in MOOD_MAP:
        return recommend_by_mood(text, user_id, reset=True)

    # 依情境推薦：電影 + 影集
    if text in SCENE_MAP:
        return recommend_by_scene(text, user_id, reset=True)

    # 口語輸入支援，例如「我想看喜劇」、「想看懸疑影集」
    all_genres = set(MOVIE_GENRE_MAP.keys())

    for genre in all_genres:
        if genre in text:
            if "影集" in text or "電視劇" in text or "劇集" in text:
                return recommend_by_genre(genre, user_id, media_type="tv", reset=True)
            if "電影" in text:
                return recommend_by_genre(genre, user_id, media_type="movie", reset=True)

            return recommend_by_genre(genre, user_id, media_type="all", reset=True)

    return (
        "我目前看不懂這個指令🥲\n\n"
        "你可以輸入「說明」查看功能，或試試：\n"
        "熱門電影、熱門影集、想放鬆、想燒腦、朋友一起看、隨機推薦。"
    )


def get_help_text():
    return (
        "我是「今晚看什麼」LINE Bot！🎬\n"
        "可以幫你推薦電影和影集。\n\n"

        "【熱門推薦】\n"
        "・熱門電影\n"
        "・熱門影集\n"
        "・熱門影視\n"
        "・隨機推薦\n\n"

        "【依類型推薦】\n"
        "・推薦喜劇\n"
        "・推薦恐怖\n"
        "・推薦愛情\n"
        "・推薦動畫\n"
        "・推薦動作\n"
        "・推薦懸疑\n"
        "・推薦科幻\n\n"

        "如果只想看電影，可以輸入：\n"
        "・推薦喜劇電影\n"
        "・推薦懸疑電影\n\n"

        "如果只想看影集，可以輸入：\n"
        "・推薦喜劇影集\n"
        "・推薦懸疑影集\n\n"

        "【依心情推薦】\n"
        "・想放鬆\n"
        "・想哭\n"
        "・想被療癒\n"
        "・想刺激\n"
        "・想燒腦\n"
        "・想浪漫\n"
        "・想熱血\n\n"

        "【依情境推薦】\n"
        "・一個人看\n"
        "・朋友一起看\n"
        "・約會看\n"
        "・睡前看\n"
        "・吃飯配片\n"
        "・假日看\n\n"

        "【查詢】\n"
        "・查電影 電影名稱\n"
        "・查影集 影集名稱\n"
        "例如：查電影 你的名字\n"
        "例如：查影集 怪奇物語\n\n"

        "每次會推薦 5 部。\n"
        "如果沒有喜歡的，可以輸入「換一批」。\n\n"
        "資料來源：TMDb"
    )


def get_popular_items(user_id, media_type="all", reset=False, title=None):
    movies = fetch_popular_items(media_type)

    if title is None:
        if media_type == "movie":
            title = "熱門電影推薦"
        elif media_type == "tv":
            title = "熱門影集推薦"
        else:
            title = "熱門影視推薦"

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "popular",
            "media_type": media_type,
            "genres": [],
            "title": title,
            "shown_ids": set()
        }

    return select_items_without_repeat(
        user_id=user_id,
        items=movies,
        title=title
    )


def recommend_by_genre(genre, user_id, media_type="all", reset=False):
    if genre not in MOVIE_GENRE_MAP and genre not in TV_GENRE_MAP:
        return (
            "目前支援的類型有：\n"
            "喜劇、恐怖、愛情、動畫、動作、懸疑、科幻、冒險、劇情、家庭、犯罪、奇幻。"
        )

    items = fetch_items_by_genres([genre], media_type)

    if media_type == "movie":
        title = f"{genre}電影推薦"
    elif media_type == "tv":
        title = f"{genre}影集推薦"
    else:
        title = f"{genre}影視推薦"

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "genre",
            "media_type": media_type,
            "genres": [genre],
            "title": title,
            "shown_ids": set()
        }

    return select_items_without_repeat(
        user_id=user_id,
        items=items,
        title=title
    )


def recommend_by_mood(mood, user_id, reset=False):
    genres = MOOD_MAP[mood]
    items = fetch_items_by_genres(genres, media_type="all")
    title = f"{mood}的影視推薦"

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "mood",
            "media_type": "all",
            "genres": genres,
            "title": title,
            "shown_ids": set()
        }

    return select_items_without_repeat(
        user_id=user_id,
        items=items,
        title=title
    )


def recommend_by_scene(scene, user_id, reset=False):
    genres = SCENE_MAP[scene]
    items = fetch_items_by_genres(genres, media_type="all")
    title = f"{scene}影視推薦"

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "scene",
            "media_type": "all",
            "genres": genres,
            "title": title,
            "shown_ids": set()
        }

    return select_items_without_repeat(
        user_id=user_id,
        items=items,
        title=title
    )


def recommend_next_batch(user_id):
    if user_id not in user_sessions:
        return (
            "你還沒有選擇推薦條件喔！\n"
            "可以先輸入：熱門電影、熱門影集、想放鬆、想燒腦、朋友一起看。"
        )

    session = user_sessions[user_id]
    mode = session["mode"]
    media_type = session["media_type"]

    if mode == "popular":
        items = fetch_popular_items(media_type)
    else:
        items = fetch_items_by_genres(session["genres"], media_type)

    return select_items_without_repeat(
        user_id=user_id,
        items=items,
        title=session["title"]
    )


def fetch_popular_items(media_type="all"):
    all_items = []

    if media_type in ["movie", "all"]:
        all_items.extend(fetch_popular_by_type("movie"))

    if media_type in ["tv", "all"]:
        all_items.extend(fetch_popular_by_type("tv"))

    all_items = filter_valid_items(all_items)

    return sorted(
        all_items,
        key=lambda item: item.get("popularity", 0),
        reverse=True
    )


def fetch_popular_by_type(media_type):
    all_items = []

    for page in range(1, 4):
        url = f"https://api.themoviedb.org/3/{media_type}/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "zh-TW",
            "page": page
        }

        response = requests.get(url, params=params)
        data = response.json()

        for item in data.get("results", []):
            item["media_type"] = media_type
            all_items.append(item)

    return all_items


def fetch_items_by_genres(genres, media_type="all"):
    all_items = []

    if media_type in ["movie", "all"]:
        all_items.extend(fetch_items_by_type_and_genres("movie", genres))

    if media_type in ["tv", "all"]:
        all_items.extend(fetch_items_by_type_and_genres("tv", genres))

    all_items = filter_valid_items(all_items)

    return sorted(
        all_items,
        key=lambda item: item.get("popularity", 0),
        reverse=True
    )


def fetch_items_by_type_and_genres(media_type, genres):
    all_items = []

    if media_type == "movie":
        genre_map = MOVIE_GENRE_MAP
    else:
        genre_map = TV_GENRE_MAP

    genre_ids = [
        str(genre_map[genre])
        for genre in genres
        if genre in genre_map
    ]

    if not genre_ids:
        return []

    genre_query = "|".join(genre_ids)

    for page in range(1, 4):
        url = f"https://api.themoviedb.org/3/discover/{media_type}"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "zh-TW",
            "with_genres": genre_query,
            "sort_by": "popularity.desc",
            "page": page
        }

        response = requests.get(url, params=params)
        data = response.json()

        for item in data.get("results", []):
            item["media_type"] = media_type
            all_items.append(item)

    return all_items


def filter_valid_items(items):
    valid_items = []

    for item in items:
        media_type = item.get("media_type")

        if media_type == "movie":
            title = item.get("title")
            date = item.get("release_date")
        else:
            title = item.get("name")
            date = item.get("first_air_date")

        overview = item.get("overview")
        item_id = item.get("id")

        if title and overview and item_id:
            item["display_title"] = title
            item["display_date"] = date or "無日期"
            valid_items.append(item)

    return valid_items


def select_items_without_repeat(user_id, items, title):
    shown_ids = user_sessions[user_id]["shown_ids"]

    available_items = [
        item for item in items
        if get_item_key(item) not in shown_ids
    ]

    if not available_items:
        user_sessions[user_id]["shown_ids"] = set()
        return (
            "目前沒有更多不重複的推薦了。\n"
            "我已經幫你重新整理片單，可以再輸入一次「換一批」。"
        )

    selected_items = available_items[:5]

    for item in selected_items:
        shown_ids.add(get_item_key(item))

    return format_item_list(selected_items, title)


def get_item_key(item):
    return f"{item.get('media_type')}_{item.get('id')}"


def search_item(keyword, media_type="movie"):
    if not keyword:
        if media_type == "movie":
            return "請輸入電影名稱，例如：查電影 你的名字"
        return "請輸入影集名稱，例如：查影集 怪奇物語"

    url = f"https://api.themoviedb.org/3/search/{media_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "zh-TW",
        "query": keyword,
        "page": 1
    }

    response = requests.get(url, params=params)
    data = response.json()

    items = []

    for item in data.get("results", []):
        item["media_type"] = media_type
        items.append(item)

    items = filter_valid_items(items)

    if not items:
        return "找不到這個作品，請換一個關鍵字試試看。"

    item = items[0]
    return format_single_item(item, "查詢結果")


def format_item_list(items, title):
    result = f"{title} 🎬\n\n"

    for i, item in enumerate(items, start=1):
        name = item.get("display_title", "無片名")
        rating = item.get("vote_average", "無評分")
        date = item.get("display_date", "無日期")
        overview = item.get("overview") or "目前沒有中文簡介。"
        media_label = "電影" if item.get("media_type") == "movie" else "影集"

        if len(overview) > 45:
            overview = overview[:45] + "……"

        result += (
            f"{i}. 【{media_label}】《{name}》\n"
            f"評分：{rating}｜日期：{date}\n"
            f"簡介：{overview}\n\n"
        )

    result += "如果沒有喜歡的，可以輸入「換一批」。\n\n"
    result += "資料來源：TMDb"
    return result


def format_single_item(item, title):
    name = item.get("display_title", "無片名")
    rating = item.get("vote_average", "無評分")
    date = item.get("display_date", "無日期")
    overview = item.get("overview") or "目前沒有中文簡介。"
    media_label = "電影" if item.get("media_type") == "movie" else "影集"

    if len(overview) > 120:
        overview = overview[:120] + "……"

    return (
        f"{title} 🎬\n\n"
        f"類型：{media_label}\n"
        f"名稱：《{name}》\n"
        f"評分：{rating}\n"
        f"日期：{date}\n"
        f"簡介：{overview}\n\n"
        f"資料來源：TMDb"
    )
