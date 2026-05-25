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
TWITTER_API_KEY            = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET         = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN       = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET= os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN       = os.getenv("TWITTER_BEARER_TOKEN")
OPENAI_API_KEY             = os.getenv("OPENAI_API_KEY")

# === SETUP CLIENTS ===
openai.api_key = OPENAI_API_KEY

# v2 client — posting, search, engagement
client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=True
)

# v1.1 API — profile updates, profile image
auth_v1 = tweepy.OAuth1UserHandler(
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
)
api_v1 = tweepy.API(auth_v1)

# === BRAND IDENTITY ===
BOT_NAME        = "XRPL Daily"
BOT_BIO         = (
    "Your daily source for XRP price analysis, XRPL ecosystem news, "
    "NFTs on the XRP Ledger & real alpha. "
    "The future of finance runs on XRPL. #XRP #XRPL"
)
BOT_LOCATION    = "XRP Ledger 🌐"

# === XRP/XRPL FOCUSED RSS FEEDS ===
RSS_FEEDS = [
    "https://ripple.com/insights/feed/",
    "https://dailyhodl.com/category/xrp/feed/",
    "https://u.today/rss",
    "https://ambcrypto.com/category/xrp/feed/",
    "https://cointelegraph.com/rss",
]

XRP_KEYWORDS = [
    "xrp", "xrpl", "ripple", "on-demand liquidity", "odl",
    "cbdc", "sec ripple", "xrp ledger", "xrp nft", "xrpl nft",
    "amm xrpl", "cross-border payment", "ripplenet", "garlinghouse",
    "david schwartz", "brad garlinghouse", "ondo", "xrp etf",
    "joelkatz", "ripplex", "xumm", "xaman", "hooks amendment",
    "xls-20", "xls-30", "xrpl dex", "tokenized", "rwa xrpl"
]

# === HIGH-PROFILE XRP/XRPL ACCOUNTS ===
TARGET_XRP_ACCOUNTS = [
    "Ripple",
    "bgarlinghouse",
    "JoelKatz",
    "RippleXDev",
    "xrpl_org",
    "WietseWind",
    "DigPerspectives",
    "moon__lambo",
    "XRPcryptowolf",
    "sentosumosaba",
    "Linqto_official",
    "CryptoEri",
    "GiantGox",
    "XRP_Updates",
    "XRP_Healthcare",
    "zerpening",
    "Hodor_XRP",
    "TplusZero",
]

# === STATE TRACKING ===
last_mention_id    = None
followed_users     = set()
engaged_tweet_ids  = set()
liked_tweet_ids    = set()
MY_USER_ID         = None


# ================================================================
#  UTILITIES
# ================================================================

def get_my_user_id():
    try:
        me = client.get_me()
        return me.data.id
    except Exception as e:
        print(f"Error getting user ID: {e}")
        return None


def get_xrp_news():
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                title   = entry.get("title", "").lower()
                summary = entry.get("summary", "").lower()
                if any(kw in title or kw in summary for kw in XRP_KEYWORDS):
                    articles.append({
                        "title":   entry.get("title", ""),
                        "link":    entry.get("link", ""),
                        "summary": entry.get("summary", "")[:200]
                    })
        except Exception as e:
            print(f"RSS error ({feed_url}): {e}")
    random.shuffle(articles)
    return articles[:6] if articles else []


def get_xrp_price():
    try:
        url    = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "ripple,bitcoin,ethereum",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_market_cap": "true"
        }
        r = requests.get(url, params=params, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Price fetch error: {e}")
        return {}


def ask_gpt(prompt, max_tokens=280):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are XRPL Daily — a sharp, credible XRP and XRPL expert account on Twitter/X. "
                        "You deeply understand: XRP Ledger consensus (RPCA), XRPL NFTs (XLS-20), "
                        "XRPL AMM (XLS-30), Ripple ODL cross-border payments, XRPL DEX, "
                        "CBDC infrastructure, SEC vs Ripple legal history, Hooks smart contracts, "
                        "RWA tokenization on XRPL (Ondo Finance etc.), and XRPL DeFi. "
                        "Your goal is to grow a massive XRP following by making bold, accurate calls "
                        "and dropping insight the community actually values. "
                        "Tweet style: punchy, confident, credible — under 260 characters. "
                        "Emojis: relevant and tasteful. Hashtags: max 2-3 from "
                        "#XRP #XRPL #Ripple #XRPCommunity #XRPLNFT #XRPArmy #Web3 #Crypto. "
                        "Never hedge everything. Make real calls. Never say 'As an AI'."
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


def post_tweet(text, reply_to_id=None):
    try:
        if not text or len(text) > 280:
            print(f"Tweet skipped — {len(text) if text else 0} chars")
            return None
        if reply_to_id:
            result = client.create_tweet(text=text, in_reply_to_tweet_id=reply_to_id)
        else:
            result = client.create_tweet(text=text)
        print(f"[{datetime.now().strftime('%H:%M')}] POSTED: {text[:80]}...")
        return result
    except Exception as e:
        print(f"Tweet error: {e}")
        return None


# ================================================================
#  BRANDING — runs once at startup
# ================================================================

def setup_xrp_profile():
    """
    Auto-brand the Twitter profile: name, bio, location.
    Uses v1.1 API (most reliable for profile field updates).
    """
    print("Setting up XRP brand profile...")
    try:
        api_v1.update_profile(
            name=BOT_NAME,
            description=BOT_BIO,
            location=BOT_LOCATION
        )
        print(f"Profile updated: '{BOT_NAME}' | bio set | location: {BOT_LOCATION}")
    except Exception as e:
        print(f"Profile setup error: {e}")


def pin_intro_tweet():
    """Post and pin a strong intro tweet establishing the account's authority."""
    try:
        intro_prompt = (
            "Write a strong, authoritative intro tweet for an XRP/XRPL expert account called 'XRPL Daily'. "
            "Establish credibility: daily XRP price analysis, XRPL ecosystem news, NFTs on XRPL, "
            "real alpha and honest calls. Make the XRP community want to follow immediately. "
            "Under 270 characters. Include #XRP #XRPL."
        )
        intro = ask_gpt(intro_prompt)
        if intro:
            result = post_tweet(intro)
            if result and result.data:
                tweet_id = result.data["id"]
                # Pin it
                client.pin_tweet(tweet_id)
                print(f"Intro tweet posted and pinned: {tweet_id}")
    except Exception as e:
        print(f"Pin tweet error: {e}")


# ================================================================
#  FOLLOW STRATEGY
# ================================================================

def follow_xrp_influencers_on_startup():
    """
    Proactively follow all target XRP influencer accounts on startup.
    Gets us into their follower notifications immediately.
    """
    print("Following XRP influencer accounts...")
    followed_count = 0
    for username in TARGET_XRP_ACCOUNTS:
        try:
            user = client.get_user(username=username)
            if user.data:
                client.follow_user(user.data.id)
                followed_users.add(user.data.id)
                followed_count += 1
                print(f"  Followed @{username}")
                time.sleep(3)  # Avoid rate limit bursts
        except Exception as e:
            print(f"  Could not follow @{username}: {e}")
    print(f"Startup follow complete: {followed_count} XRP accounts followed.")


def follow_back_followers():
    """Follow back every new follower."""
    global MY_USER_ID
    if not MY_USER_ID:
        return
    try:
        followers = client.get_users_followers(id=MY_USER_ID, max_results=100)
        if not followers.data:
            return
        new_follows = 0
        for follower in followers.data:
            if follower.id not in followed_users:
                try:
                    client.follow_user(follower.id)
                    followed_users.add(follower.id)
                    new_follows += 1
                    time.sleep(2)
                except Exception as e:
                    print(f"Follow-back error: {e}")
        if new_follows > 0:
            print(f"[{datetime.now().strftime('%H:%M')}] Followed back {new_follows} new follower(s).")
    except Exception as e:
        print(f"Follow-back error: {e}")


def strategic_follow_xrp_community():
    """
    Follow people who are actively engaging with XRP content.
    These are warm leads — they're already in the community and likely to follow back.
    """
    global MY_USER_ID
    try:
        query = '(#XRP OR #XRPL OR "$XRP") -is:retweet lang:en'
        tweets = client.search_recent_tweets(
            query=query,
            max_results=20,
            tweet_fields=["author_id", "public_metrics"]
        )
        if not tweets.data:
            return

        followed_count = 0
        for tweet in tweets.data:
            author_id = tweet.author_id
            if (author_id not in followed_users
                    and str(author_id) != str(MY_USER_ID)):
                try:
                    client.follow_user(author_id)
                    followed_users.add(author_id)
                    followed_count += 1
                    time.sleep(3)
                    if followed_count >= 5:  # Cap per run to stay safe
                        break
                except Exception as e:
                    print(f"Strategic follow error: {e}")

        if followed_count > 0:
            print(f"[{datetime.now().strftime('%H:%M')}] Strategically followed {followed_count} XRP community member(s).")
    except Exception as e:
        print(f"Strategic follow error: {e}")


# ================================================================
#  ENGAGEMENT ENGINE — the follower growth core
# ================================================================

def engage_with_top_xrp_content():
    """
    Find the highest-engagement XRP tweets and drop a sharp reply.
    Your reply appears under viral XRP content — millions of eyeballs.
    """
    global engaged_tweet_ids, MY_USER_ID
    try:
        query = '(#XRP OR #XRPL OR "XRP Ledger" OR "$XRP") -is:retweet lang:en'
        tweets = client.search_recent_tweets(
            query=query,
            max_results=25,
            tweet_fields=["public_metrics", "author_id", "text", "created_at"],
            sort_order="relevancy"
        )
        if not tweets.data:
            return

        candidates = [
            t for t in tweets.data
            if str(t.author_id) != str(MY_USER_ID)
            and t.id not in engaged_tweet_ids
        ]

        def score(t):
            m = t.public_metrics
            return (m.get("like_count", 0)
                    + m.get("retweet_count", 0) * 2
                    + m.get("reply_count", 0))

        candidates.sort(key=score, reverse=True)

        replied = 0
        for tweet in candidates[:3]:
            if score(tweet) < 10:
                continue
            prompt = (
                f"This XRP/XRPL tweet has {score(tweet)} engagement: '{tweet.text}'. "
                f"Write a reply under 235 chars that: "
                f"1) Adds a fact or sharper angle they missed, "
                f"2) Shows deep XRP/XRPL knowledge, "
                f"3) Makes their followers want to click your profile. "
                f"Be confident and specific. No flattery."
            )
            reply = ask_gpt(prompt, max_tokens=200)
            if reply:
                result = post_tweet(reply, reply_to_id=tweet.id)
                if result:
                    engaged_tweet_ids.add(tweet.id)
                    replied += 1
                    time.sleep(15)

        # Trim history set
        if len(engaged_tweet_ids) > 500:
            engaged_tweet_ids = set(list(engaged_tweet_ids)[-500:])

        print(f"[{datetime.now().strftime('%H:%M')}] Replied to {replied} top XRP tweet(s).")
    except Exception as e:
        print(f"Top content engagement error: {e}")


def engage_with_xrp_influencers():
    """
    Reply directly to recent tweets from top XRP accounts.
    A smart reply under Garlinghouse or JoelKatz gets seen by millions.
    """
    global engaged_tweet_ids, MY_USER_ID
    targets = random.sample(TARGET_XRP_ACCOUNTS, min(3, len(TARGET_XRP_ACCOUNTS)))
    replied = 0

    for username in targets:
        try:
            user = client.get_user(username=username)
            if not user.data:
                continue

            tweets = client.get_users_tweets(
                id=user.data.id,
                max_results=5,
                tweet_fields=["public_metrics", "text"],
                exclude=["retweets", "replies"]
            )
            if not tweets.data:
                continue

            best = max(
                tweets.data,
                key=lambda t: (t.public_metrics.get("like_count", 0)
                               + t.public_metrics.get("retweet_count", 0) * 2)
            )

            if best.id in engaged_tweet_ids:
                continue
            if best.public_metrics.get("like_count", 0) < 5:
                continue

            likes = best.public_metrics.get("like_count", 0)
            prompt = (
                f"@{username} tweeted: '{best.text}' ({likes} likes). "
                f"Write a reply under 235 chars that adds genuine insight — "
                f"a fact, a sharper take, or a real XRPL detail their audience will value. "
                f"Sound like a knowledgeable peer, not a fan."
            )
            reply = ask_gpt(prompt, max_tokens=200)
            if reply:
                result = post_tweet(reply, reply_to_id=best.id)
                if result:
                    engaged_tweet_ids.add(best.id)
                    replied += 1
                    time.sleep(20)

        except Exception as e:
            print(f"Influencer engage error (@{username}): {e}")
            continue

    print(f"[{datetime.now().strftime('%H:%M')}] Replied to {replied} influencer tweet(s).")


def like_top_xrp_content():
    """
    Like high-engagement XRP tweets.
    Liking puts your account name in the author's notifications —
    repeated likes build recognition and often earn a follow-back.
    """
    global liked_tweet_ids, MY_USER_ID
    try:
        query = '(#XRP OR #XRPL OR "$XRP") -is:retweet lang:en'
        tweets = client.search_recent_tweets(
            query=query,
            max_results=20,
            tweet_fields=["public_metrics", "author_id"],
            sort_order="relevancy"
        )
        if not tweets.data:
            return

        liked = 0
        for tweet in tweets.data:
            if (tweet.id not in liked_tweet_ids
                    and str(tweet.author_id) != str(MY_USER_ID)):
                likes = tweet.public_metrics.get("like_count", 0)
                if likes >= 20:  # Only like content with real traction
                    try:
                        client.like(MY_USER_ID, tweet.id)
                        liked_tweet_ids.add(tweet.id)
                        liked += 1
                        time.sleep(3)
                        if liked >= 10:  # Cap per run
                            break
                    except Exception as e:
                        print(f"Like error: {e}")

        if len(liked_tweet_ids) > 1000:
            liked_tweet_ids = set(list(liked_tweet_ids)[-1000:])

        if liked > 0:
            print(f"[{datetime.now().strftime('%H:%M')}] Liked {liked} top XRP tweet(s).")
    except Exception as e:
        print(f"Like error: {e}")


def reply_to_mentions():
    """Reply to all new mentions, prioritizing highest-engagement ones first."""
    global last_mention_id, MY_USER_ID
    if not MY_USER_ID:
        return
    try:
        kwargs = {
            "id": MY_USER_ID,
            "max_results": 10,
            "tweet_fields": ["author_id", "text", "public_metrics"]
        }
        if last_mention_id:
            kwargs["since_id"] = last_mention_id

        mentions = client.get_users_mentions(**kwargs)
        if not mentions.data:
            print("No new mentions.")
            return

        last_mention_id = mentions.data[0].id

        # Prioritize by engagement
        sorted_mentions = sorted(
            mentions.data,
            key=lambda t: (
                t.public_metrics.get("like_count", 0)
                if hasattr(t, "public_metrics") and t.public_metrics else 0
            ),
            reverse=True
        )

        for mention in sorted_mentions:
            prompt = (
                f"Someone replied to your XRP tweet: '{mention.text}'. "
                f"Write a knowledgeable, genuine reply under 235 chars. "
                f"Add insight they didn't have. Don't start with 'Great question'."
            )
            reply = ask_gpt(prompt, max_tokens=200)
            if reply:
                post_tweet(reply, reply_to_id=mention.id)
                time.sleep(5)

        print(f"[{datetime.now().strftime('%H:%M')}] Replied to {len(mentions.data)} mention(s).")
    except Exception as e:
        print(f"Mentions error: {e}")


# ================================================================
#  DAILY CONTENT SCHEDULE
# ================================================================

def morning_xrp_prices():
    prices = get_xrp_price()
    if not prices:
        return
    xrp      = prices.get("ripple", {})
    btc      = prices.get("bitcoin", {})
    xrp_p    = xrp.get("usd", 0)
    xrp_chg  = xrp.get("usd_24h_change", 0)
    xrp_mcap = xrp.get("usd_market_cap", 0)
    btc_chg  = btc.get("usd_24h_change", 0)
    prompt = (
        f"Morning XRP market briefing. Data: XRP=${xrp_p:.4f} ({xrp_chg:+.1f}% 24h), "
        f"Market cap ${xrp_mcap/1e9:.1f}B. BTC {btc_chg:+.1f}% today. "
        f"Write a sharp morning update — include a brief take on what the price action signals."
    )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)


def xrp_news_morning():
    articles = get_xrp_news()
    if not articles:
        prompt = (
            "Write a tweet about why XRP is uniquely positioned to win the global payment "
            "infrastructure race — mention ODL, bank adoption, or CBDC partnerships specifically."
        )
    else:
        article = articles[0]
        prompt = (
            f"XRP/XRPL news: '{article['title']}'. "
            f"Write a tweet with an honest expert take — what does this actually mean "
            f"for XRP holders? Be direct. Make a call — bullish, bearish, or neutral and why."
        )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)


def xrp_community_engagement():
    topics = [
        "Ask the XRP community: What's your realistic XRP price target this cycle? Give your reasoning — no moon math.",
        "Write a tweet asking: Which XRP/XRPL development excites you most right now — XRPL AMM, Hooks, RWA tokenization, or CBDC rails?",
        "Ask: How long have you held XRP and what was your entry? Let the community share their stories.",
        "Write a tweet: Do you think XRPL DeFi (AMM + DEX + Hooks) will pull liquidity away from Ethereum? Make your case.",
        "Ask the XRP army: What's the one catalyst that sends XRP past $5 — ETF, Ripple IPO, or mass bank ODL adoption?",
        "Write a tweet: Are you adding XRP at current levels or waiting? What's your actual strategy?",
        "Ask: What XRPL ecosystem project besides Ripple itself are you most bullish on right now?",
        "Write: If XRP captures even 10% of the $150T cross-border payment market, what does that mean for price? Let's do the math.",
    ]
    tweet = ask_gpt(random.choice(topics))
    if tweet:
        post_tweet(tweet)


def midday_xrp_update():
    prices = get_xrp_price()
    if not prices:
        return
    xrp     = prices.get("ripple", {})
    btc     = prices.get("bitcoin", {})
    xrp_p   = xrp.get("usd", 0)
    xrp_chg = xrp.get("usd_24h_change", 0)
    btc_chg = btc.get("usd_24h_change", 0)
    outperform = "outperforming" if xrp_chg > btc_chg else "underperforming"
    prompt = (
        f"Midday XRP check: XRP=${xrp_p:.4f} ({xrp_chg:+.1f}%), BTC {btc_chg:+.1f}%. "
        f"XRP is {outperform} BTC today. Write a punchy midday update with a quick take on what that means. Under 210 chars."
    )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)


def xrp_news_afternoon():
    articles = get_xrp_news()
    if not articles:
        prompt = (
            "Write a tweet about Ripple's expanding ODL corridors and what it means for "
            "real XRP utility and price support. Be specific — name a region or corridor."
        )
    else:
        article = random.choice(articles)
        prompt = (
            f"Breaking XRP/XRPL news: '{article['title']}'. "
            f"Write a hot take tweet — is this bullish, bearish, or neutral for XRP? "
            f"Give one specific reason. Don't hedge. Make the call."
        )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)


def xrpl_education():
    topics = [
        "Explain what the XRP Ledger consensus (RPCA) is and why it settles in 3-5 seconds with near-zero fees — far better than ETH for payments.",
        "Write a tweet explaining XRPL NFTs (XLS-20) — why minting on XRPL costs fractions of a cent vs hundreds on Ethereum.",
        "Explain Ripple ODL — how XRP acts as a real-time bridge currency between fiat corridors. Give a specific payment example.",
        "Write a tweet on the XRPL AMM (XLS-30) — what DeFi it unlocks on the XRP Ledger and why it matters for liquidity.",
        "Explain the Ripple vs SEC ruling and what legal clarity means for XRP listings on US exchanges.",
        "Write a tweet on the XRPL DEX — a built-in decentralized exchange directly on the ledger. Why is this a big deal?",
        "Explain how the XRP Ledger is being used for CBDC infrastructure. Name real country/central bank examples.",
        "Write a tweet on Ondo Finance bringing tokenized US Treasuries to XRPL — why institutions care about this.",
        "Explain XRPL Hooks — the upcoming smart contract layer on XRP Ledger and what it will allow developers to build.",
        "Write a tweet: XRP has been burning ~0.00001 XRP per transaction since 2013. With billions of transactions, what does that mean for supply?",
    ]
    tweet = ask_gpt(random.choice(topics))
    if tweet:
        post_tweet(tweet)


def xrp_market_commentary():
    prices   = get_xrp_price()
    articles = get_xrp_news()
    xrp      = prices.get("ripple", {})
    xrp_p    = xrp.get("usd", 0) or 0.50
    xrp_chg  = xrp.get("usd_24h_change", 0)
    news_ctx = articles[0]["title"] if articles else "XRP ecosystem development continues"
    prompt = (
        f"Evening XRP analysis. XRP=${xrp_p:.4f} ({xrp_chg:+.1f}% today). "
        f"Context: {news_ctx}. "
        f"Write a confident, specific market commentary tweet. "
        f"Make a call or observation — where is XRP likely heading and why? Build credibility."
    )
    tweet = ask_gpt(prompt)
    if tweet:
        post_tweet(tweet)


def xrpl_alpha():
    insights = [
        "Share a contrarian XRP take most people dismiss — back it with a specific fact or on-chain data point.",
        "Write a tweet spotlighting an underrated XRPL ecosystem project or development. Be specific — name it.",
        "Share your honest bull case for XRP over the next 12-18 months. Not hype — actual catalysts with specifics.",
        "Write a tweet on the biggest XRP catalyst being ignored by mainstream crypto Twitter right now.",
        "Share something specific about XRPL NFTs that most crypto people don't know — a feature, stat, or project.",
        "Write a tweet: what does a spot XRP ETF approval actually do to XRP price and adoption? Make a real projection.",
        "Share an insight on how RWA tokenization on XRPL could bring trillions in TradFi value onto the ledger.",
        "Write a tweet: if Ripple goes public via IPO, what specifically happens to XRP credibility and price? Make the case.",
        "Share a precise technical advantage XRPL has over Ethereum or Solana for settlement. Be specific, not generic.",
        "Write a late-night alpha tweet: one XRPL development in the next 12 months that will matter most and why.",
    ]
    tweet = ask_gpt(random.choice(insights))
    if tweet:
        post_tweet(tweet)


# ================================================================
#  SCHEDULER ENTRYPOINT
# ================================================================

def run_scheduler():
    global MY_USER_ID

    print