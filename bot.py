import tweepy
import openai
import requests
import schedule
import time
import os
import random
import feedparser
from datetime import datetime

# === CREDENTIALS FROM ENVIRONMENT ===
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === SETUP CLIENTS ===
openai.api_key = OPENAI_API_KEY

client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=True
)

# === RSS FEEDS ===
RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
]

def get_crypto_news():
    """Fetch latest crypto news from RSS feeds."""
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                articles.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", "")[:200]
                })
        except Exception as e:
            print(f"RSS error: {e}")
    return articles[:5] if articles else []

def get_crypto_prices():
    """Fetch live crypto prices from CoinGecko (free, no key needed)."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin,ethereum,solana,cardano,ripple",
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        r = requests.get(url, params=params, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Price fetch error: {e}")
        return {}

def ask_gpt(prompt, max_tokens=280):
    """Ask GPT-4o-mini to generate tweet content."""
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a crypto & finance expert Twitter influencer. "
                        "Write punchy, engaging tweets under 260 characters. "
                        "Use relevant emojis. No hashtags spam — max 2. "
                        "Be authoritative but accessible. Never use 'As an AI'."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.85
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"GPT error: {e}")
        return None

def post_tweet(text):
    """Post a tweet and log it."""
    try:
        if not text or len(text) > 280:
            print(f"Tweet skipped — length issue: {len(text) if text else 0} chars")
            return
        result = client.create_tweet(text=text)
        print(f"[{datetime.now().strftime('%H:%M')}] POSTED: {text[:80]}...")
        return result
    except Exception as e:
        print(f"Tweet error: {e}")
        return None

# === SCHEDULED TWEET FUNCTIONS ===

def morning_prices():
    """7am — Morning market prices."""
    prices = get_crypto_prices()
    if not prices:
        return
    btc = prices.get("bitcoin", {})
    eth = prices.get("ethereum", {})
    sol = prices.get("solana", {})
    btc_price = btc.get("usd", 0)
    btc_change = btc.get("usd_24h_change", 0)
    eth_price = eth.get("usd", 0)
    sol_price = sol.get("usd", 0)
    direction = "📈" if btc_change > 0 else "📉"
    prompt = (
        f"Write a morning crypto market update tweet. Current prices: "
        f"BTC=${btc_price:,.0f} ({btc_change:+.1f}%), ETH=${eth_price:,.0f}, SOL=${sol_price:.2f}. "
        f"Make it feel like an exciting morning briefing."
    )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)

def news_thread_morning():
    """9am — Morning news thread."""
    articles = get_crypto_news()
    if not articles:
        return
    article = random.choice(articles)
    prompt = (
        f"Write a tweet about this crypto news: '{article['title']}'. "
        f"Add your expert take. Make it engaging and insightful."
    )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)

def engagement_tweet():
    """11am — Engagement / poll / question tweet."""
    topics = [
        "Ask your followers: Which crypto will outperform in the next 6 months? BTC, ETH, SOL, or an altcoin?",
        "Write a tweet asking: Is now a good time to DCA into Bitcoin? Get the community talking.",
        "Ask your audience: What's the biggest mistake new crypto investors make?",
        "Poll question: What percentage of your portfolio is crypto? Get people to reply.",
        "Write a controversial but true statement about crypto investing that will spark debate.",
        "Ask: What was your first crypto purchase? Get the community to share their story.",
    ]
    prompt = random.choice(topics)
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)

def midday_prices():
    """1pm — Midday price check."""
    prices = get_crypto_prices()
    if not prices:
        return
    btc = prices.get("bitcoin", {})
    eth = prices.get("ethereum", {})
    btc_price = btc.get("usd", 0)
    btc_change = btc.get("usd_24h_change", 0)
    eth_price = eth.get("usd", 0)
    prompt = (
        f"Write a quick midday crypto market update. BTC=${btc_price:,.0f} ({btc_change:+.1f}% today), "
        f"ETH=${eth_price:,.0f}. Keep it short and punchy — under 200 chars."
    )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)

def news_thread_afternoon():
    """3pm — Afternoon news thread."""
    articles = get_crypto_news()
    if not articles:
        return
    article = random.choice(articles)
    prompt = (
        f"Breaking crypto news: '{article['title']}'. "
        f"Write a tweet with your hot take on what this means for investors."
    )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)

def educational_thread():
    """5pm — Educational crypto content."""
    topics = [
        "Explain Bitcoin halving and why it matters for price — in simple terms for beginners.",
        "Explain what DeFi is and why it's revolutionary, in a tweet for someone who has never heard of it.",
        "Write a tweet explaining why dollar-cost averaging (DCA) is a powerful crypto strategy.",
        "Explain what a crypto wallet is — hot vs cold — and why it matters for security.",
        "Explain what on-chain metrics are and why smart investors follow them.",
        "Write a tweet explaining the difference between a coin and a token.",
        "Explain what Bitcoin's Lightning Network does and why it's important.",
        "Write a tweet explaining why crypto is volatile and how to mentally handle it.",
    ]
    prompt = random.choice(topics)
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)

def ai_commentary():
    """8pm — AI commentary on market/trends."""
    prices = get_crypto_prices()
    articles = get_crypto_news()
    btc_price = prices.get("bitcoin", {}).get("usd", 65000)
    btc_change = prices.get("bitcoin", {}).get("usd_24h_change", 0)
    news_context = articles[0]["title"] if articles else "crypto market volatility"
    prompt = (
        f"Write an insightful evening market commentary tweet. "
        f"BTC is at ${btc_price:,.0f} ({btc_change:+.1f}% today). "
        f"Recent news: {news_context}. "
        f"Share a unique perspective or prediction that sounds smart and confident."
    )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)

def alpha_insight():
    """10pm — Alpha / insider-style insight."""
    insights = [
        "Share a contrarian take on crypto that most people overlook but sophisticated investors know.",
        "Write a tweet with a specific crypto insight or pattern you're watching right now.",
        "Share one thing about Bitcoin that Wall Street doesn't want retail investors to understand.",
        "Write a tweet with a bullish long-term crypto thesis — make it sound exclusive and insightful.",
        "Share an underrated metric or indicator that smart crypto investors track.",
        "Write a tweet about the biggest risk in crypto right now that nobody is talking about.",
    ]
    prompt = random.choice(insights)
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)

# === SCHEDULE ===
def run_scheduler():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] CryptoFlowBot scheduler started.")
    print("Scheduled posts: 7am, 9am, 11am, 1pm, 3pm, 5pm, 8pm, 10pm daily.")
    print("="*50)

    schedule.every().day.at("07:00").do(morning_prices)
    schedule.every().day.at("09:00").do(news_thread_morning)
    schedule.every().day.at("11:00").do(engagement_tweet)
    schedule.every().day.at("13:00").do(midday_prices)
    schedule.every().day.at("15:00").do(news_thread_afternoon)
    schedule.every().day.at("17:00").do(educational_thread)
    schedule.every().day.at("20:00").do(ai_commentary)
    schedule.every().day.at("22:00").do(alpha_insight)

    # Post one immediately on startup to test
    print("Posting startup test tweet...")
    prices = get_crypto_prices()
    btc = prices.get("bitcoin", {})
    btc_price = btc.get("usd", 0)
    btc_change = btc.get("usd_24h_change", 0)
    if btc_price:
        startup_prompt = (
            f"Write a tweet announcing you're live and sharing the latest BTC price: "
            f"${btc_price:,.0f} ({btc_change:+.1f}% today). "
            f"Make it exciting like you just went live on a finance show."
        )
    else:
        startup_prompt = "Write a tweet introducing yourself as a crypto market expert who posts daily insights, prices, and alpha."
    startup_tweet = ask_gpt(startup_prompt)
    if startup_tweet:
        post_tweet(startup_tweet)

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    run_scheduler()
