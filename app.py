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


GENRE_MAP = {
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


# 心情對應到電影類型
MOOD_MAP = {
    "想放鬆": ["喜劇", "動畫", "家庭"],
    "想哭": ["劇情", "愛情"],
    "想被療癒": ["動畫", "家庭", "劇情"],
    "想刺激": ["恐怖", "動作"],
    "想燒腦": ["懸疑", "科幻", "犯罪"],
    "想浪漫": ["愛情", "喜劇"],
    "想熱血": ["動作", "冒險"],
}


# 情境對應到電影類型
SCENE_MAP = {
    "一個人看": ["懸疑", "劇情", "科幻"],
    "朋友一起看": ["喜劇", "動作", "動畫"],
    "約會看": ["愛情", "喜劇", "動畫"],
    "睡前看": ["動畫", "家庭", "喜劇"],
    "吃飯配片": ["喜劇", "動畫", "冒險"],
    "假日看": ["冒險", "動作", "喜劇"],
}


# 記住使用者上一輪看過哪些電影，讓「換一批」不要重複
user_sessions = {}


@app.route("/", methods=["GET"])
def home():
    return "Movie LINE Bot is running."


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
    if text == "說明":
        return get_help_text()

    if text == "熱門電影":
        return get_popular_movie(user_id, reset=True)

    if text in ["隨機推薦", "幫我選", "隨便推薦"]:
        return get_random_recommendation(user_id, reset=True)

    if text in ["換一批", "繼續推薦", "再推薦"]:
        return recommend_next_batch(user_id)

    if text.startswith("推薦"):
        genre = text.replace("推薦", "").strip()
        return recommend_by_genre(genre, user_id, reset=True)

    if text in MOOD_MAP:
        return recommend_by_mood(text, user_id, reset=True)

    if text in SCENE_MAP:
        return recommend_by_scene(text, user_id, reset=True)

    if text.startswith("查電影 "):
        keyword = text.replace("查電影 ", "", 1).strip()
        return search_movie(keyword)

    # 支援比較口語的輸入
    for genre in GENRE_MAP:
        if genre in text:
            return recommend_by_genre(genre, user_id, reset=True)

    return (
        "我目前看不懂這個指令🥲\n\n"
        "你可以輸入「說明」查看功能，或試試：\n"
        "熱門電影、想放鬆、想燒腦、朋友一起看、隨機推薦。"
    )


def get_help_text():
    return (
        "我是「今晚看什麼」LINE Bot！🎬\n\n"
        "你可以這樣使用我：\n\n"
        "【熱門推薦】\n"
        "・熱門電影\n"
        "・隨機推薦\n\n"
        "【依類型推薦】\n"
        "・推薦喜劇\n"
        "・推薦恐怖\n"
        "・推薦愛情\n"
        "・推薦動畫\n"
        "・推薦動作\n"
        "・推薦懸疑\n"
        "・推薦科幻\n\n"
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
        "【查詢電影】\n"
        "・查電影 電影名稱\n"
        "例如：查電影 你的名字\n\n"
        "每次會推薦 5 部電影。\n"
        "如果沒有喜歡的，可以輸入「換一批」。\n\n"
        "資料來源：TMDb"
    )


def get_popular_movie(user_id, reset=False):
    movies = fetch_popular_movies()

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "popular",
            "genres": [],
            "title": "熱門電影推薦",
            "shown_ids": set()
        }

    return select_movies_without_repeat(
        user_id=user_id,
        movies=movies,
        title="熱門電影推薦"
    )


def get_random_recommendation(user_id, reset=False):
    movies = fetch_popular_movies()

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "random",
            "genres": [],
            "title": "今晚隨機推薦",
            "shown_ids": set()
        }

    return select_movies_without_repeat(
        user_id=user_id,
        movies=movies,
        title="今晚隨機推薦"
    )


def recommend_by_genre(genre, user_id, reset=False):
    if genre not in GENRE_MAP:
        return (
            "目前支援的類型有：\n"
            "喜劇、恐怖、愛情、動畫、動作、懸疑、科幻、冒險、劇情、家庭、犯罪、奇幻。"
        )

    movies = fetch_movies_by_genres([genre])

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "genre",
            "genres": [genre],
            "title": f"{genre}電影推薦",
            "shown_ids": set()
        }

    return select_movies_without_repeat(
        user_id=user_id,
        movies=movies,
        title=f"{genre}電影推薦"
    )


def recommend_by_mood(mood, user_id, reset=False):
    genres = MOOD_MAP[mood]
    movies = fetch_movies_by_genres(genres)

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "mood",
            "genres": genres,
            "title": f"{mood}的電影推薦",
            "shown_ids": set()
        }

    return select_movies_without_repeat(
        user_id=user_id,
        movies=movies,
        title=f"{mood}的電影推薦"
    )


def recommend_by_scene(scene, user_id, reset=False):
    genres = SCENE_MAP[scene]
    movies = fetch_movies_by_genres(genres)

    if reset or user_id not in user_sessions:
        user_sessions[user_id] = {
            "mode": "scene",
            "genres": genres,
            "title": f"{scene}電影推薦",
            "shown_ids": set()
        }

    return select_movies_without_repeat(
        user_id=user_id,
        movies=movies,
        title=f"{scene}電影推薦"
    )


def recommend_next_batch(user_id):
    if user_id not in user_sessions:
        return (
            "你還沒有選擇推薦條件喔！\n"
            "可以先輸入：熱門電影、想放鬆、想燒腦、朋友一起看、推薦喜劇。"
        )

    session = user_sessions[user_id]
    mode = session["mode"]

    if mode in ["popular", "random"]:
        movies = fetch_popular_movies()
    else:
        movies = fetch_movies_by_genres(session["genres"])

    return select_movies_without_repeat(
        user_id=user_id,
        movies=movies,
        title=session["title"]
    )


def fetch_popular_movies():
    all_movies = []

    for page in range(1, 4):
        url = "https://api.themoviedb.org/3/movie/popular"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "zh-TW",
            "page": page
        }

        response = requests.get(url, params=params)
        data = response.json()
        all_movies.extend(data.get("results", []))

    return filter_valid_movies(all_movies)


def fetch_movies_by_genres(genres):
    all_movies = []

    genre_ids = [str(GENRE_MAP[genre]) for genre in genres if genre in GENRE_MAP]
    genre_query = "|".join(genre_ids)

    for page in range(1, 4):
        url = "https://api.themoviedb.org/3/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "language": "zh-TW",
            "with_genres": genre_query,
            "sort_by": "popularity.desc",
            "page": page
        }

        response = requests.get(url, params=params)
        data = response.json()
        all_movies.extend(data.get("results", []))

    return filter_valid_movies(all_movies)


def filter_valid_movies(movies):
    valid_movies = []

    for movie in movies:
        title = movie.get("title")
        overview = movie.get("overview")
        movie_id = movie.get("id")

        if title and overview and movie_id:
            valid_movies.append(movie)

    return valid_movies


def select_movies_without_repeat(user_id, movies, title):
    shown_ids = user_sessions[user_id]["shown_ids"]

    available_movies = [
        movie for movie in movies
        if movie.get("id") not in shown_ids
    ]

    if not available_movies:
        user_sessions[user_id]["shown_ids"] = set()
        return (
            "目前沒有更多不重複的推薦了。\n"
            "我已經幫你重新整理片單，可以再輸入一次「換一批」。"
        )

    selected_movies = available_movies[:5]

    for movie in selected_movies:
        shown_ids.add(movie.get("id"))

    return format_movie_list(selected_movies, title)


def search_movie(keyword):
    if not keyword:
        return "請輸入電影名稱，例如：查電影 你的名字"

    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "zh-TW",
        "query": keyword,
        "page": 1
    }

    response = requests.get(url, params=params)
    data = response.json()

    movies = data.get("results", [])
    movies = filter_valid_movies(movies)

    if not movies:
        return "找不到這部電影，請換一個關鍵字試試看。"

    movie = movies[0]
    return format_single_movie(movie, "電影查詢結果")


def format_movie_list(movies, title):
    result = f"{title} 🎬\n\n"

    for i, movie in enumerate(movies, start=1):
        name = movie.get("title", "無片名")
        rating = movie.get("vote_average", "無評分")
        date = movie.get("release_date", "無上映日期")
        overview = movie.get("overview") or "目前沒有中文簡介。"

        if len(overview) > 45:
            overview = overview[:45] + "……"

        result += (
            f"{i}. 《{name}》\n"
            f"評分：{rating}｜上映：{date}\n"
            f"簡介：{overview}\n\n"
        )

    result += "如果沒有喜歡的，可以輸入「換一批」。\n\n"
    result += "資料來源：TMDb"
    return result


def format_single_movie(movie, title):
    name = movie.get("title", "無片名")
    rating = movie.get("vote_average", "無評分")
    date = movie.get("release_date", "無上映日期")
    overview = movie.get("overview") or "目前沒有中文簡介。"

    if len(overview) > 120:
        overview = overview[:120] + "……"

    return (
        f"{title} 🎬\n\n"
        f"片名：《{name}》\n"
        f"評分：{rating}\n"
        f"上映日期：{date}\n"
        f"簡介：{overview}\n\n"
        f"資料來源：TMDb"
    )
