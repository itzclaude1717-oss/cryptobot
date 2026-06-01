"""
XRPL Daily — AI Agent v2
========================
Full AI agent that pulls LIVE data from:
  • XRPL Ledger (xrpl-py) — DEX, AMM, NFT sales, on-chain stats
  • CoinGecko — XRP price, trending XRPL tokens, market data
  • XRP Scan / Bithomp — NFT collections, dApps, top accounts
  • RSS / Crypto news — real-time XRPL headlines
  • Twitter/X search — trending XRP community content

Then uses GPT-4 to generate original, engaging posts & replies
and autonomously engages the XRP community 24/7.
"""

import os, time, random, json, re, logging, traceback
import requests, feedparser, httpx, schedule
import tweepy
from openai import OpenAI
from datetime import datetime, timezone, timedelta

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("XRPLAgent")

# ── Credentials ──────────────────────────────────────────────────────────────
TWITTER_API_KEY             = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET          = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN        = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN        = os.getenv("TWITTER_BEARER_TOKEN")
OPENAI_API_KEY              = os.getenv("OPENAI_API_KEY")

# ── Clients ───────────────────────────────────────────────────────────────────
gpt = OpenAI(api_key=OPENAI_API_KEY, http_client=httpx.Client(trust_env=False))

twitter = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=True,
)

auth_v1 = tweepy.OAuth1UserHandler(
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET,
)
api_v1 = tweepy.API(auth_v1)

# ── Bot Identity ──────────────────────────────────────────────────────────────
BOT_NAME     = "XRPL Daily"
BOT_BIO      = (
    "🌐 Live XRPL intelligence | XRP price · top tokens · NFTs · dApps · alpha\n"
    "AI-powered. Community-first. #XRP #XRPL #Ripple"
)
BOT_LOCATION = "XRP Ledger 🌐"
MY_USER_ID   = None   # filled in at startup

# ── Key XRP accounts to engage ────────────────────────────────────────────────
XRP_INFLUENCERS = [
    "Ripple", "bgarlinghouse", "JoelKatz", "RippleXDev", "xrpl_org",
    "WietseWind", "JackTheRippler", "DigPerspectives", "CryptoEri",
    "WrathofKahneman", "moon__lambo", "GiantGox", "XRPcryptowolf",
    "sentosumosaba", "zerpening", "TplusZero", "XRP_Updates",
    "Hodor_XRP", "Leonidas_io", "nbougalis", "Pro_XRPL",
    "XRPHealthcare", "Linqto_official", "CryptoInsider21",
]

# ── RSS feeds ─────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://ripple.com/insights/feed/",
    "https://dailyhodl.com/category/xrp/feed/",
    "https://u.today/rss",
    "https://ambcrypto.com/category/xrp/feed/",
    "https://cointelegraph.com/rss",
    "https://cryptoslate.com/feed/",
    "https://decrypt.co/feed",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]

XRP_KEYWORDS = {
    "xrp", "xrpl", "ripple", "xrp ledger", "odl", "on-demand liquidity",
    "cbdc", "sec ripple", "xrp nft", "amm xrpl", "ripplenet",
    "garlinghouse", "joelkatz", "ripplex", "xumm", "xaman",
    "xls-20", "xls-30", "xrpl dex", "tokenized", "rwa xrpl",
    "xrp etf", "ondo xrpl", "xrpl hooks", "xrp price",
}

# ── State (in-memory, avoids file I/O issues on Railway) ────────────────────
_liked_tweet_ids   = set()
_replied_tweet_ids = set()
_followed_users    = set()
_posted_news_urls  = set()
_last_mention_id   = None


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  LIVE DATA LAYER
# ╚══════════════════════════════════════════════════════════════════════════════

def fetch_xrp_price() -> dict:
    """CoinGecko — XRP price + 24h change + market cap."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "ripple", "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true"},
            timeout=10,
        )
        d = r.json()["ripple"]
        return {
            "price": d.get("usd", 0),
            "change_24h": d.get("usd_24h_change", 0),
            "market_cap": d.get("usd_market_cap", 0),
            "volume_24h": d.get("usd_24h_vol", 0),
        }
    except Exception as e:
        log.warning(f"XRP price fetch failed: {e}")
        return {}


def fetch_trending_xrpl_tokens() -> list[dict]:
    """CoinGecko — trending coins on XRPL / top gainers in crypto."""
    tokens = []
    try:
        # Trending search on CoinGecko
        r = requests.get(
            "https://api.coingecko.com/api/v3/search/trending",
            timeout=10,
        )
        for item in r.json().get("coins", [])[:10]:
            c = item.get("item", {})
            tokens.append({
                "name":   c.get("name", ""),
                "symbol": c.get("symbol", ""),
                "rank":   c.get("market_cap_rank", "?"),
                "score":  c.get("score", 0),
            })
    except Exception as e:
        log.warning(f"Trending tokens fetch failed: {e}")

    # Also fetch top XRPL DEX tokens via xrpscan
    try:
        r2 = requests.get(
            "https://api.xrpscan.com/api/v1/well-known",
            timeout=10,
        )
        for acct in r2.json()[:5]:
            if acct.get("domain"):
                tokens.append({
                    "name":    acct.get("name", ""),
                    "account": acct.get("account", ""),
                    "domain":  acct.get("domain", ""),
                    "source":  "xrpscan",
                })
    except Exception as e:
        log.warning(f"XRPScan well-known fetch failed: {e}")

    return tokens


def fetch_xrpl_ledger_stats() -> dict:
    """XRPL public API — live ledger stats, TPS, AMM pools."""
    stats = {}
    try:
        # Latest ledger info via public rippled node
        r = requests.post(
            "https://xrplcluster.com",
            json={"method": "server_info", "params": [{}]},
            timeout=10,
        )
        info = r.json().get("result", {}).get("info", {})
        stats["ledger_index"]   = info.get("validated_ledger", {}).get("seq", "?")
        stats["tps"]            = info.get("load_factor", "?")
        stats["server_state"]   = info.get("server_state", "?")
        stats["peers"]          = info.get("peers", "?")
        stats["fee_base"]       = info.get("validated_ledger", {}).get("base_fee_xrp", "?")
    except Exception as e:
        log.warning(f"XRPL ledger stats failed: {e}")

    try:
        # AMM info — get a list of recent AMM pools
        r2 = requests.post(
            "https://xrplcluster.com",
            json={"method": "amm_info", "params": [{"ledger_index": "validated"}]},
            timeout=10,
        )
        amm = r2.json().get("result", {})
        if "amm" in amm:
            stats["amm_pools"] = amm["amm"]
    except Exception as e:
        log.warning(f"AMM info failed: {e}")

    return stats


def fetch_xrpl_nft_sales() -> list[dict]:
    """XRP Scan — recent NFT sales on the XRPL."""
    sales = []
    try:
        r = requests.get(
            "https://api.xrpscan.com/api/v1/nft/sales",
            params={"limit": 10},
            timeout=10,
        )
        for s in r.json()[:5]:
            sales.append({
                "nft_id":     s.get("NFTokenID", "")[:16] + "...",
                "price_xrp":  s.get("amount_xrp", 0),
                "seller":     s.get("seller", ""),
                "buyer":      s.get("buyer", ""),
                "collection": s.get("collection", {}).get("name", "Unknown"),
            })
    except Exception as e:
        log.warning(f"NFT sales fetch failed: {e}")
    return sales


def fetch_xrpl_dapps() -> list[dict]:
    """Fetch known XRPL dApps / ecosystem projects."""
    # Curated + live from xrpl.org ecosystem
    curated = [
        {"name": "Xaman (XUMM)", "category": "Wallet", "url": "https://xaman.app"},
        {"name": "XRPLto",       "category": "Analytics", "url": "https://xrpl.to"},
        {"name": "Magnetic X",   "category": "DEX",      "url": "https://magnetic.app"},
        {"name": "Sologenic",    "category": "DEX/NFT",  "url": "https://sologenic.com"},
        {"name": "XRPL.org DEX", "category": "DEX",      "url": "https://xrpl.org/decentralized-exchange.html"},
        {"name": "Evernode",     "category": "Smart Contracts", "url": "https://evernode.org"},
        {"name": "XLS-30 AMM",   "category": "AMM",      "url": "https://xrpl.org/amm.html"},
        {"name": "Crossmark",    "category": "Wallet",   "url": "https://crossmark.io"},
        {"name": "GemWallet",    "category": "Wallet",   "url": "https://gemwallet.app"},
        {"name": "Aesthetes",    "category": "NFT Marketplace", "url": "https://aesthetes.art"},
        {"name": "XPmarket",     "category": "NFT Marketplace", "url": "https://xpmarket.com"},
        {"name": "onXRP",        "category": "NFT/DEX",  "url": "https://onxrp.com"},
        {"name": "First Ledger", "category": "Launchpad","url": "https://firstledger.net"},
        {"name": "XRPL Commons", "category": "Community","url": "https://xrplcommons.com"},
    ]
    random.shuffle(curated)
    return curated[:5]


def fetch_xrp_news() -> list[dict]:
    """RSS — latest XRPL/XRP headlines filtered to be relevant."""
    articles = []
    seen_titles = set()
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title   = entry.get("title", "")
                summary = entry.get("summary", "")
                link    = entry.get("link", "")
                text    = (title + " " + summary).lower()
                if any(kw in text for kw in XRP_KEYWORDS):
                    if title not in seen_titles and link not in _posted_news_urls:
                        seen_titles.add(title)
                        articles.append({
                            "title":   title,
                            "summary": summary[:300],
                            "link":    link,
                            "source":  feed.feed.get("title", url),
                        })
        except Exception as e:
            log.warning(f"RSS {url} failed: {e}")
    random.shuffle(articles)
    return articles[:8]


def fetch_trending_xrp_tweets() -> list[dict]:
    """Twitter v2 search — find high-engagement XRP tweets to react to."""
    tweets = []
    queries = [
        "#XRP -is:retweet lang:en",
        "#XRPL -is:retweet lang:en",
        "XRP price -is:retweet lang:en",
        "XRPL NFT -is:retweet lang:en",
        "XRP ledger dapp -is:retweet lang:en",
    ]
    query = random.choice(queries)
    try:
        results = twitter.search_recent_tweets(
            query=query,
            max_results=10,
            tweet_fields=["public_metrics", "author_id", "text", "id"],
            sort_order="relevancy",
        )
        if results.data:
            for t in results.data:
                m = t.public_metrics
                if m and (m.get("like_count", 0) + m.get("retweet_count", 0)) > 5:
                    tweets.append({
                        "id":       str(t.id),
                        "text":     t.text,
                        "likes":    m.get("like_count", 0),
                        "retweets": m.get("retweet_count", 0),
                        "author":   str(t.author_id),
                    })
    except Exception as e:
        log.warning(f"Tweet search failed: {e}")
    return tweets


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  AI CONTENT ENGINE
# ╚══════════════════════════════════════════════════════════════════════════════

def ai(system: str, user: str, max_tokens: int = 280) -> str:
    """Call GPT-4o with a system + user prompt. Returns clean text."""
    try:
        resp = gpt.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.85,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"GPT call failed: {e}")
        return ""


SYSTEM_VOICE = """You are XRPL Daily — a sharp, knowledgeable, community-loved XRP/XRPL Twitter account.
Your voice is: confident, informative, hype where warranted, never spammy.
You use relevant emojis sparingly (1-3 per tweet). You use hashtags: #XRP #XRPL at end if space permits.
STRICT RULE: All tweets MUST be under 280 characters. Never use placeholder text like [price] — only use actual numbers from the data provided.
Never make up prices or stats. If data is missing, pivot to insight/opinion."""

SYSTEM_REPLY = """You are XRPL Daily — a real, engaged XRP community member replying to tweets.
Your replies are: genuine, adds value, occasionally witty. NEVER sycophantic. Max 220 characters.
You support XRP but aren't a mindless cheerleader — you add insight.
STRICT RULE: Reply must be under 220 characters. Sound human, not like a bot."""


def generate_price_post(price_data: dict) -> str:
    price    = price_data.get("price", 0)
    change   = price_data.get("change_24h", 0)
    mcap     = price_data.get("market_cap", 0)
    volume   = price_data.get("volume_24h", 0)
    arrow    = "📈" if change >= 0 else "📉"
    sign     = "+" if change >= 0 else ""
    mcap_b   = f"${mcap/1e9:.2f}B" if mcap > 1e9 else f"${mcap/1e6:.0f}M"
    vol_b    = f"${volume/1e9:.2f}B" if volume > 1e9 else f"${volume/1e6:.0f}M"

    return ai(SYSTEM_VOICE,
        f"""Write a punchy XRP price update tweet using EXACTLY these live numbers:
Price: ${price:.4f}
24h change: {sign}{change:.2f}%
Market cap: {mcap_b}
24h volume: {vol_b}
Arrow emoji to use: {arrow}
Include the actual numbers. Under 280 chars."""
    )


def generate_news_post(article: dict) -> str:
    return ai(SYSTEM_VOICE,
        f"""Write a tweet about this XRPL news. Be informative and create urgency.
Title: {article['title']}
Summary: {article['summary']}
Source: {article['source']}
Add the link at the end: {article['link']}
Under 280 chars total.""",
        max_tokens=320,
    )


def generate_nft_post(sales: list[dict]) -> str:
    if not sales:
        return ai(SYSTEM_VOICE,
            "Write a hype tweet about XRPL NFTs being one of the most underrated NFT ecosystems. Under 260 chars."
        )
    top = sorted(sales, key=lambda x: x.get("price_xrp", 0), reverse=True)[:3]
    sales_text = "\n".join(
        f"• {s['collection']}: {s['price_xrp']} XRP" for s in top
    )
    return ai(SYSTEM_VOICE,
        f"""Write an engaging tweet about these recent XRPL NFT sales:
{sales_text}
Highlight the value/momentum. Under 260 chars."""
    )


def generate_dapp_post(dapps: list[dict]) -> str:
    featured = dapps[:3]
    dapp_text = "\n".join(f"• {d['name']} ({d['category']})" for d in featured)
    return ai(SYSTEM_VOICE,
        f"""Write an educational tweet spotlighting these XRPL dApps/ecosystem projects:
{dapp_text}
Show why the XRPL ecosystem is thriving. Under 260 chars. Include one of their categories."""
    )


def generate_meme_token_post(tokens: list[dict]) -> str:
    xrpl_tokens = [t for t in tokens if t.get("source") != "xrpscan"][:5]
    trending    = tokens[:5]
    token_text  = "\n".join(
        f"• {t.get('name','?')} (${t.get('symbol','?')}) — rank #{t.get('rank','?')}"
        for t in trending
    )
    return ai(SYSTEM_VOICE,
        f"""Write a tweet about trending crypto tokens and tie it back to the XRPL ecosystem.
Current trending tokens in crypto:
{token_text}
Angle: XRPL is the infrastructure for the next wave of tokenization. Under 265 chars."""
    )


def generate_alpha_post(ledger: dict) -> str:
    idx = ledger.get("ledger_index", "?")
    fee = ledger.get("fee_base", "?")
    return ai(SYSTEM_VOICE,
        f"""Write an XRPL alpha/insight tweet. Use these live ledger stats:
Current ledger: #{idx}
Base fee: {fee} XRP (essentially free)
Server state: {ledger.get('server_state', 'full')}
Angle: XRPL's speed, cost, and reliability vs other chains. Under 260 chars."""
    )


def generate_engagement_post() -> str:
    """Community question / poll-style tweet to drive engagement."""
    topics = [
        "What's the most underrated XRPL dApp right now?",
        "Which XRPL NFT collection is most undervalued?",
        "What will XRP's price be EOY?",
        "Best use case for XRPL: payments, DeFi, NFTs, or RWA tokenization?",
        "Which XRPL wallet do you use daily?",
        "What XRPL ecosystem news are you most excited about?",
        "Will XRP break ATH this cycle?",
        "Most bullish XRPL catalyst right now?",
    ]
    topic = random.choice(topics)
    return ai(SYSTEM_VOICE,
        f"""Write a community engagement tweet for XRP holders around this topic: '{topic}'
Make it conversational, invites replies. Under 240 chars."""
    )


def generate_reply(tweet_text: str) -> str:
    return ai(SYSTEM_REPLY,
        f"""Generate a genuine, value-adding reply to this XRP tweet. Be specific to the content.
Tweet: "{tweet_text[:300]}"
Reply (under 220 chars, no hashtag spam):"""
    )


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  POSTING & ENGAGEMENT
# ╚══════════════════════════════════════════════════════════════════════════════

def post_tweet(text: str, source: str = "") -> bool:
    """Post a tweet. Returns True on success."""
    if not text or len(text) > 280:
        log.warning(f"Tweet skipped — empty or too long ({len(text)} chars): {text[:60]}")
        return False
    try:
        resp = twitter.create_tweet(text=text)
        tweet_id = resp.data["id"]
        log.info(f"✅ POSTED [{source}]: {text[:80]}...")
        return True
    except tweepy.errors.Forbidden as e:
        log.warning(f"Tweet forbidden (duplicate?): {e}")
        return False
    except Exception as e:
        log.error(f"Tweet failed: {e}")
        return False


def like_tweet(tweet_id: str, user_id: str) -> None:
    if tweet_id in _liked_tweet_ids:
        return
    try:
        twitter.like(tweet_id=tweet_id, user_auth=True)
        _liked_tweet_ids.add(tweet_id)
        log.info(f"❤️  Liked tweet {tweet_id}")
    except Exception as e:
        log.warning(f"Like failed {tweet_id}: {e}")


def reply_to_tweet(tweet_id: str, tweet_text: str) -> None:
    if tweet_id in _replied_tweet_ids:
        return
    reply = generate_reply(tweet_text)
    if not reply:
        return
    try:
        twitter.create_tweet(text=reply, in_reply_to_tweet_id=tweet_id)
        _replied_tweet_ids.add(tweet_id)
        log.info(f"💬 Replied to {tweet_id}: {reply[:60]}")
    except Exception as e:
        log.warning(f"Reply failed {tweet_id}: {e}")


def follow_user(user_id: str) -> None:
    if user_id in _followed_users or user_id == str(MY_USER_ID):
        return
    try:
        twitter.follow_user(target_user_id=user_id)
        _followed_users.add(user_id)
        log.info(f"➕ Followed user {user_id}")
    except Exception as e:
        log.warning(f"Follow failed {user_id}: {e}")


def retweet(tweet_id: str) -> None:
    try:
        twitter.retweet(tweet_id=tweet_id)
        log.info(f"🔁 Retweeted {tweet_id}")
    except Exception as e:
        log.warning(f"Retweet failed {tweet_id}: {e}")


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SCHEDULED TASKS
# ╚══════════════════════════════════════════════════════════════════════════════

def task_price_update():
    """Post a live XRP price update."""
    log.info("--- Price update ---")
    data = fetch_xrp_price()
    if not data:
        return
    text = generate_price_post(data)
    post_tweet(text, "price")


def task_news_post():
    """Post the freshest XRPL news article."""
    log.info("--- News post ---")
    articles = fetch_xrp_news()
    if not articles:
        log.info("No new articles found")
        return
    for article in articles:
        if article["link"] not in _posted_news_urls:
            text = generate_news_post(article)
            if post_tweet(text, "news"):
                _posted_news_urls.add(article["link"])
                break


def task_nft_post():
    """Post about XRPL NFT sales."""
    log.info("--- NFT post ---")
    sales = fetch_xrpl_nft_sales()
    text  = generate_nft_post(sales)
    post_tweet(text, "nft")


def task_dapp_post():
    """Spotlight XRPL dApps."""
    log.info("--- dApp spotlight ---")
    dapps = fetch_xrpl_dapps()
    text  = generate_dapp_post(dapps)
    post_tweet(text, "dapp")


def task_token_post():
    """Post about trending/meme tokens on XRPL."""
    log.info("--- Token/meme post ---")
    tokens = fetch_trending_xrpl_tokens()
    text   = generate_meme_token_post(tokens)
    post_tweet(text, "tokens")


def task_alpha_post():
    """Post live XRPL ledger alpha."""
    log.info("--- Alpha/ledger post ---")
    ledger = fetch_xrpl_ledger_stats()
    text   = generate_alpha_post(ledger)
    post_tweet(text, "alpha")


def task_engagement_post():
    """Post a community engagement question."""
    log.info("--- Engagement post ---")
    text = generate_engagement_post()
    post_tweet(text, "engagement")


def task_engage_trending():
    """Like and reply to trending XRP tweets."""
    log.info("--- Engaging trending XRP tweets ---")
    tweets = fetch_trending_xrp_tweets()
    if not tweets:
        return
    # Sort by engagement
    tweets.sort(key=lambda t: t.get("likes", 0) + t.get("retweets", 0) * 3, reverse=True)
    replied = 0
    for t in tweets[:5]:
        tweet_id   = t["id"]
        tweet_text = t["text"]
        # Always like high-quality content
        like_tweet(tweet_id, t["author"])
        # Reply to top tweets (max 2 per cycle to avoid spam)
        if replied < 2 and tweet_id not in _replied_tweet_ids:
            time.sleep(random.uniform(8, 20))
            reply_to_tweet(tweet_id, tweet_text)
            replied += 1
        time.sleep(random.uniform(3, 8))


def task_engage_influencers():
    """Like and occasionally reply to influencer tweets."""
    log.info("--- Engaging influencers ---")
    sample = random.sample(XRP_INFLUENCERS, min(5, len(XRP_INFLUENCERS)))
    for username in sample:
        try:
            results = twitter.search_recent_tweets(
                query=f"from:{username} -is:retweet",
                max_results=3,
                tweet_fields=["public_metrics", "id", "text"],
            )
            if results.data:
                for t in results.data[:2]:
                    like_tweet(str(t.id), "")
                    time.sleep(random.uniform(5, 15))
        except Exception as e:
            log.warning(f"Influencer engage {username}: {e}")
        time.sleep(random.uniform(10, 25))


def task_reply_mentions():
    """Reply to mentions of our account."""
    global _last_mention_id
    log.info("--- Checking mentions ---")
    try:
        me = twitter.get_me()
        kwargs = {
            "tweet_fields": ["id", "text", "author_id"],
            "max_results": 5,
        }
        if _last_mention_id:
            kwargs["since_id"] = _last_mention_id
        mentions = twitter.get_users_mentions(id=me.data.id, **kwargs)
        if mentions.data:
            for m in mentions.data:
                if str(m.id) not in _replied_tweet_ids:
                    reply = generate_reply(m.text)
                    if reply:
                        twitter.create_tweet(text=reply, in_reply_to_tweet_id=m.id)
                        _replied_tweet_ids.add(str(m.id))
                        log.info(f"📨 Replied to mention {m.id}")
                        time.sleep(random.uniform(10, 30))
            _last_mention_id = str(mentions.data[0].id)
    except Exception as e:
        log.warning(f"Mentions check failed: {e}")


def task_follow_back():
    """Follow back users who followed us and engage with XRP content."""
    log.info("--- Follow-back check ---")
    try:
        me = twitter.get_me()
        followers = twitter.get_users_followers(
            id=me.data.id,
            max_results=20,
            user_fields=["id", "name"],
        )
        if followers.data:
            for user in followers.data[:5]:
                uid = str(user.id)
                if uid not in _followed_users and uid != str(MY_USER_ID):
                    follow_user(uid)
                    time.sleep(random.uniform(5, 15))
    except Exception as e:
        log.warning(f"Follow-back failed: {e}")


def task_strategic_follows():
    """Follow key XRP accounts we haven't followed yet."""
    log.info("--- Strategic follows ---")
    sample = random.sample(XRP_INFLUENCERS, min(5, len(XRP_INFLUENCERS)))
    for username in sample:
        try:
            user = twitter.get_user(username=username)
            if user.data:
                uid = str(user.data.id)
                if uid not in _followed_users:
                    follow_user(uid)
                    time.sleep(random.uniform(8, 20))
        except Exception as e:
            log.warning(f"Strategic follow {username}: {e}")


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  STARTUP
# ╚══════════════════════════════════════════════════════════════════════════════

def setup_profile():
    """Set Twitter profile to XRPL Daily brand."""
    try:
        api_v1.update_profile(
            name=BOT_NAME,
            description=BOT_BIO,
            location=BOT_LOCATION,
        )
        log.info(f"✅ Profile updated: '{BOT_NAME}'")
    except Exception as e:
        log.warning(f"Profile update failed: {e}")


def check_auth() -> bool:
    try:
        me = api_v1.verify_credentials()
        if me:
            global MY_USER_ID
            MY_USER_ID = me.id
            log.info(f"✅ Auth OK — logged in as @{me.screen_name} (ID: {me.id})")
            return True
    except Exception as e:
        log.error(f"❌ Auth FAILED: {e}")
    return False


def post_startup_tweet():
    """Post a live-data-powered startup tweet."""
    data = fetch_xrp_price()
    if data:
        price  = data.get("price", 0)
        change = data.get("change_24h", 0)
        sign   = "+" if change >= 0 else ""
        arrow  = "📈" if change >= 0 else "📉"
        text = ai(SYSTEM_VOICE,
            f"""Write a welcome/startup tweet for XRPL Daily with live data:
XRP price right now: ${price:.4f} ({sign}{change:.2f}%) {arrow}
Announce we're live and covering XRPL: prices, NFTs, dApps, meme tokens, alpha. Under 265 chars."""
        )
    else:
        text = (
            "🚀 XRPL Daily is LIVE — your AI-powered source for real-time XRP prices, "
            "XRPL NFTs, dApps, trending tokens & ecosystem alpha. Let's run it. "
            "#XRP #XRPL"
        )
    post_tweet(text, "startup")


def build_schedule():
    """Register all scheduled tasks."""

    # Price updates — 4x/day at key market times
    schedule.every().day.at("07:00").do(task_price_update)
    schedule.every().day.at("12:00").do(task_price_update)
    schedule.every().day.at("17:00").do(task_price_update)
    schedule.every().day.at("21:00").do(task_price_update)

    # News — every 3 hours
    schedule.every(3).hours.do(task_news_post)

    # NFT update — twice a day
    schedule.every().day.at("09:30").do(task_nft_post)
    schedule.every().day.at("19:00").do(task_nft_post)

    # dApp spotlight — once a day
    schedule.every().day.at("11:00").do(task_dapp_post)

    # Trending tokens — once a day
    schedule.every().day.at("14:00").do(task_token_post)

    # Alpha / ledger stats — twice a day
    schedule.every().day.at("08:00").do(task_alpha_post)
    schedule.every().day.at("20:00").do(task_alpha_post)

    # Community engagement posts — twice a day
    schedule.every().day.at("10:00").do(task_engagement_post)
    schedule.every().day.at("18:00").do(task_engagement_post)

    # Engage trending XRP tweets — every 30 min
    schedule.every(30).minutes.do(task_engage_trending)

    # Engage influencers — every 90 min
    schedule.every(90).minutes.do(task_engage_influencers)

    # Reply to mentions — every 20 min
    schedule.every(20).minutes.do(task_reply_mentions)

    # Follow-back — every 2 hours
    schedule.every(2).hours.do(task_follow_back)

    # Strategic follows — every 4 hours
    schedule.every(4).hours.do(task_strategic_follows)

    log.info("📅 Schedule active:")
    log.info("  Price updates:      07:00 12:00 17:00 21:00")
    log.info("  News posts:         every 3h")
    log.info("  NFT updates:        09:30 19:00")
    log.info("  dApp spotlight:     11:00")
    log.info("  Token/meme post:    14:00")
    log.info("  Alpha posts:        08:00 20:00")
    log.info("  Engagement posts:   10:00 18:00")
    log.info("  Engage trending:    every 30 min")
    log.info("  Engage influencers: every 90 min")
    log.info("  Reply mentions:     every 20 min")
    log.info("  Follow-back:        every 2h")
    log.info("  Strategic follows:  every 4h")


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  MAIN
# ╚══════════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info(f"XRPL Daily AI Agent v2 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    log.info("=" * 60)

    if not check_auth():
        log.error("Aborting — Twitter auth failed. Check credentials.")
        return

    setup_profile()

    # Initial burst of content right after startup
    log.info("Running startup content burst...")
    post_startup_tweet()
    time.sleep(10)
    task_news_post()
    time.sleep(10)
    task_alpha_post()
    time.sleep(10)
    task_engage_trending()
    time.sleep(10)
    task_strategic_follows()

    build_schedule()

    log.info("=" * 60)
    log.info("✅ XRPL Daily AI Agent is running. Waiting for scheduled tasks...")
    log.info("=" * 60)

    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            log.info("Shutting down...")
            break
        except Exception as e:
            log.error(f"Main loop error: {e}\n{traceback.format_exc()}")
            time.sleep(60)


if __name__ == "__main__":
    main()
