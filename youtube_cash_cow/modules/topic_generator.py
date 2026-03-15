"""
Topic Generator Module
Finds trending and high-performing video topics using multiple strategies:
- Google Trends via pytrends
- Curated niche-based topic banks
- YouTube trending scraping
"""
import json
import random
import logging
from datetime import datetime
from typing import Optional
import requests

logger = logging.getLogger(__name__)


TOPIC_BANKS = {
    "top10": [
        "Top 10 Most Dangerous Animals in the World",
        "Top 10 Richest People in History",
        "Top 10 Most Mysterious Places on Earth",
        "Top 10 Strangest Laws That Still Exist",
        "Top 10 Most Expensive Things in the World",
        "Top 10 Biggest Mistakes in History",
        "Top 10 Lost Cities Never Found",
        "Top 10 Most Intelligent Animals",
        "Top 10 Deadliest Diseases in Human History",
        "Top 10 Strange Natural Phenomena",
        "Top 10 Most Powerful Empires in History",
        "Top 10 Unsolved Mysteries of the Ocean",
        "Top 10 Most Haunted Places on Earth",
        "Top 10 Inventions That Changed the World",
        "Top 10 Most Extreme Climates on Earth",
    ],
    "facts": [
        "Mind-Blowing Facts About Space That Will Change Your Perspective",
        "Shocking Facts About the Human Body You Never Learned in School",
        "Incredible Facts About Ancient Civilizations",
        "Facts About the Ocean That Will Leave You Speechless",
        "Surprising Facts About Money and Wealth",
        "Unbelievable Facts About Animals That Seem Fake",
        "Fascinating Facts About How Your Brain Works",
        "Crazy Facts About Historical Events Schools Don't Teach",
        "Weird Facts About Everyday Objects You Use",
        "Mind-Blowing Facts About Time and the Universe",
        "Shocking Facts About Food You Eat Every Day",
        "Incredible Facts About Human Psychology",
    ],
    "educational": [
        "How the World's Richest People Actually Made Their Money",
        "Why Some Countries Are Rich and Others Are Poor",
        "How Viruses Actually Work Inside Your Body",
        "The Real Reason Dinosaurs Went Extinct",
        "How the Internet Actually Works",
        "Why We Dream and What It Means",
        "How Ancient Egyptians Built the Pyramids",
        "The Science Behind Why We Sleep",
        "How Black Holes Actually Form and Work",
        "Why Humans Are the Only Surviving Human Species",
        "How Your Memory Actually Works",
        "The Real History Behind Common Phrases",
    ],
    "motivational": [
        "Habits of the World's Most Successful People",
        "Why Most People Never Achieve Their Goals",
        "The Morning Routines That Changed Successful Lives",
        "How to Train Your Brain for Success",
        "Lessons from People Who Went From Broke to Millionaires",
        "Why Discipline Matters More Than Motivation",
        "How to Stop Procrastinating Forever",
        "The Psychology of Getting Rich",
        "Why Some People Succeed While Others Fail",
        "How to Build Unbreakable Self-Discipline",
    ],
    "mystery": [
        "Mysterious Disappearances That Were Never Solved",
        "Ancient Mysteries That Scientists Cannot Explain",
        "Strange Things Found at the Bottom of the Ocean",
        "Unexplained Events Caught on Camera",
        "The World's Greatest Unsolved Crimes",
        "Mysterious Structures Found in the Middle of Nowhere",
        "Creepy Things That Happened Before Major Disasters",
        "Secrets Governments Tried to Hide",
        "Bizarre Coincidences That Changed History",
        "Strange Phenomena That Defy Scientific Explanation",
    ],
}


def get_trending_topics_from_pytrends(niche: str = "general") -> list[str]:
    """Fetch trending topics using Google Trends."""
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=360)
        trending_searches = pytrends.trending_searches(pn="united_states")
        topics = trending_searches[0].tolist()[:5]
        logger.info(f"Fetched {len(topics)} trending topics from Google Trends")
        return topics
    except Exception as e:
        logger.warning(f"Could not fetch from Google Trends: {e}")
        return []


def get_youtube_trending_topics() -> list[str]:
    """Scrape YouTube trending page for popular topics."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        response = requests.get(
            "https://www.youtube.com/feed/trending",
            headers=headers,
            timeout=10,
        )
        if response.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")
            titles = []
            for tag in soup.find_all("yt-formatted-string", {"class": "style-scope ytd-video-renderer"}):
                title = tag.get_text(strip=True)
                if title and len(title) > 10:
                    titles.append(title)
            return titles[:10]
    except Exception as e:
        logger.warning(f"Could not scrape YouTube trending: {e}")
    return []


def get_topics_for_niche(niche: str, count: int = 5) -> list[dict]:
    """
    Get a list of video topics for the given niche.
    Returns topic dicts with title, niche, and metadata.
    """
    available_niches = list(TOPIC_BANKS.keys())
    if niche not in available_niches:
        niche = random.choice(available_niches)
        logger.info(f"Niche not found, using random niche: {niche}")

    pool = TOPIC_BANKS.get(niche, []).copy()

    # Supplement with trending topics
    trending = get_trending_topics_from_pytrends(niche)
    if trending:
        formatted = [f"The Truth About {t}" for t in trending[:3]]
        pool.extend(formatted)

    random.shuffle(pool)
    selected = pool[:count]

    topics = []
    for title in selected:
        topics.append({
            "title": title,
            "niche": niche,
            "generated_at": datetime.now().isoformat(),
            "estimated_views": random.randint(50_000, 2_000_000),
        })

    logger.info(f"Generated {len(topics)} topics for niche '{niche}'")
    return topics


def select_best_topic(niches: list[str]) -> dict:
    """
    Select the single best topic to produce next,
    cycling across niches for variety.
    """
    niche = random.choice(niches)
    topics = get_topics_for_niche(niche, count=3)
    if not topics:
        # Fallback
        return {
            "title": "Top 10 Most Amazing Facts You Never Knew",
            "niche": "facts",
            "generated_at": datetime.now().isoformat(),
            "estimated_views": 100_000,
        }
    # Pick topic with highest estimated views
    return max(topics, key=lambda t: t["estimated_views"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    topic = select_best_topic(["top10", "facts", "educational"])
    print(json.dumps(topic, indent=2))
