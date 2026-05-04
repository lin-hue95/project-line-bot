from flask import Flask, request, abort
import os
import requests
import random

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
    "科幻": 878
}

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
    reply_text = handle_user_text(user_text)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

def handle_user_text(text):
    if text == "說明":
        return (
            "我是「今晚看什麼」LINE Bot！🎬\n\n"
            "你可以輸入：\n"
            "1. 熱門電影\n"
            "2. 推薦喜劇\n"
            "3. 推薦恐怖\n"
            "4. 推薦愛情\n"
            "5. 推薦動畫\n"
            "6. 推薦動作\n"
            "7. 推薦懸疑\n"
            "8. 推薦科幻\n"
            "9. 查電影 電影名稱\n\n"
            "例如：查電影 你的名字\n\n"
            "資料來源：TMDb"
        )

    if text == "熱門電影":
        return get_popular_movie()

    if text.startswith("推薦"):
        genre = text.replace("推薦", "").strip()
        return recommend_by_genre(genre)

    if text.startswith("查電影 "):
        keyword = text.replace("查電影 ", "", 1).strip()
        return search_movie(keyword)

    return "我看不懂這個指令，可以輸入「說明」查看功能。"

def get_popular_movie():
    url = "https://api.themoviedb.org/3/movie/popular"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "zh-TW",
        "page": 1
    }

    response = requests.get(url, params=params)
    data = response.json()

    movies = data.get("results", [])
    if not movies:
        return "目前找不到熱門電影資料。"

    movie = random.choice(movies[:10])
    return format_movie(movie, "熱門電影推薦")

def recommend_by_genre(genre):
    if genre not in GENRE_MAP:
        return "目前支援的類型有：喜劇、恐怖、愛情、動畫、動作、懸疑、科幻。"

    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "zh-TW",
        "with_genres": GENRE_MAP[genre],
        "sort_by": "popularity.desc",
        "page": 1
    }

    response = requests.get(url, params=params)
    data = response.json()

    movies = data.get("results", [])
    if not movies:
        return f"目前找不到{genre}電影。"

    movie = random.choice(movies[:10])
    return format_movie(movie, f"{genre}電影推薦")

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
    if not movies:
        return "找不到這部電影，請換一個關鍵字試試看。"

    movie = movies[0]
    return format_movie(movie, "電影查詢結果")

def get_reason(movie):
    overview = movie.get("overview") or ""

    if "恐怖" in overview or "驚悚" in overview:
        return "推薦理由：適合想看緊張、刺激劇情的時候。"
    elif "愛" in overview or "戀" in overview:
        return "推薦理由：適合想看情感線或浪漫故事的時候。"
    elif "冒險" in overview:
        return "推薦理由：適合想看節奏明快、有探索感的故事。"
    else:
        return "推薦理由：這部電影近期關注度不低，可以當作片單參考。"

def format_movie(movie, title):
    name = movie.get("title", "無片名")
    rating = movie.get("vote_average", "無評分")
    date = movie.get("release_date", "無上映日期")
    overview = movie.get("overview") or "目前沒有中文簡介。"

    if len(overview) > 120:
        overview = overview[:120] + "……"

    reason = get_reason(movie)

    return (
        f"{title}\n\n"
        f"片名：《{name}》\n"
        f"評分：{rating}\n"
        f"上映日期：{date}\n"
        f"簡介：{overview}\n\n"
        f"{reason}\n\n"
        f"資料來源：TMDb"
    )

if __name__ == "__main__":
    app.run(port=5000)
