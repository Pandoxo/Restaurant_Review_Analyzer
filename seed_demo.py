"""
Demo Data Seeder — Generates realistic synthetic data so you can preview
the dashboard without any API keys.

Usage:
    python seed_demo.py         # Seed 5 restaurants with ~200 reviews each
    python seed_demo.py --clean # Wipe DB and re-seed
"""

import argparse
import json
import random
import hashlib
import os
from datetime import datetime, timedelta

from db import get_db, init_db, insert_restaurant, insert_review, insert_analysis
from config import DB_PATH


# ── Synthetic Restaurant Data ──────────────────────────────

DEMO_RESTAURANTS = [
    {
        "place_id": "demo_001",
        "name": "Ratuszova Restaurant",
        "address": "Stary Rynek 55, 61-001 Poznań",
        "rating": 4.6,
        "total_reviews": 892,
        "lat": 52.4082,
        "lng": 16.9335,
        "has_campaign": True,
        "campaign_staff": ["Kacper", "Ania"],
        "campaign_start": datetime(2025, 3, 10),
        "campaign_duration_days": 21,
    },
    {
        "place_id": "demo_002",
        "name": "Pierogowa Chata",
        "address": "ul. Wrocławska 12, 61-838 Poznań",
        "rating": 4.3,
        "total_reviews": 1150,
        "lat": 52.4035,
        "lng": 16.9248,
        "has_campaign": True,
        "campaign_staff": ["Mateusz", "Ola", "Bartek"],
        "campaign_start": datetime(2025, 6, 1),
        "campaign_duration_days": 14,
    },
    {
        "place_id": "demo_003",
        "name": "Bamberka Bistro",
        "address": "ul. Półwiejska 42, 61-888 Poznań",
        "rating": 4.8,
        "total_reviews": 634,
        "lat": 52.4020,
        "lng": 16.9310,
        "has_campaign": False,
        "campaign_staff": [],
        "campaign_start": None,
        "campaign_duration_days": 0,
    },
    {
        "place_id": "demo_004",
        "name": "Stary Browar Grill",
        "address": "ul. Paderewskiego 8, 61-770 Poznań",
        "rating": 4.1,
        "total_reviews": 1430,
        "lat": 52.4003,
        "lng": 16.9278,
        "has_campaign": True,
        "campaign_staff": ["Zosia"],
        "campaign_start": datetime(2025, 9, 15),
        "campaign_duration_days": 10,
    },
    {
        "place_id": "demo_005",
        "name": "Kozia Broda",
        "address": "ul. Jaskółcza 17, 61-001 Poznań",
        "rating": 4.5,
        "total_reviews": 780,
        "lat": 52.4095,
        "lng": 16.9355,
        "has_campaign": False,
        "campaign_staff": [],
        "campaign_start": None,
        "campaign_duration_days": 0,
    },
]

# ── Review Templates ────────────────────────────────────────

GENUINE_TEMPLATES = [
    "Bardzo dobre jedzenie. {dish} był wyśmienity. Polecam!",
    "Byliśmy tu na kolacji. {dish} i {dish2} — naprawdę smaczne. Ceny ok.",
    "Klimat super, obsługa szybka. {dish} trochę za słony ale ogólnie dobrze.",
    "Średnio. Czekaliśmy 40 minut na {dish}. Smak w porządku ale nie wow.",
    "Fantastyczne miejsce! {dish} najlepszy w Poznaniu. Wrócimy na pewno.",
    "Niestety rozczarowanie. {dish} był zimny, kelner nieuprzejmy.",
    "Solidna kuchnia polska. {dish} jak u babci. Atmosfera przytulna.",
    "Za drogie jak na jakość. {dish} za 45zł to przesada.",
    "Idealne na randkę. Piękne wnętrze, {dish} rewelacyjny, wino doskonałe.",
    "Dobre ale nic specjalnego. {dish} był ok. Lokalizacja fajna.",
    "Polecam gorąco! {dish} i {dish2} na najwyższym poziomie.",
    "Nie wrócę. {dish} niesmaczny, rachunek zawyżony, obsługa opryskliwa.",
]

GENUINE_WITH_STAFF = [
    "Kelner {staff} bardzo profesjonalny. {dish} pyszny, polecam!",
    "Obsługa super, szczególnie {staff} — bardzo pomocny. {dish} doskonały.",
    "{staff} polecił {dish} i miał rację — rewelacja!",
]

FAKE_TEMPLATES = [
    "Super miejsce! {staff} jest najlepszy!!! Polecam!!!",
    "Najlepsza restauracja w Poznaniu! {staff} nas obsługiwał, cudownie!",
    "Byliśmy i {staff} zadbał o nas rewelacyjnie. 5 gwiazdek!",
    "{staff} to najlepszy kelner jakiego spotkałam! Gorąco polecam!",
    "Rewelacja! Dzięki {staff} mieliśmy wspaniały wieczór! Wrócę!",
    "Polecam! Obsługa {staff} na najwyższym poziomie!!!",
    "Cudowne miejsce, {staff} zadbał o każdy szczegół. TOP!!!",
    "{staff} jest niesamowity! Najlepsza obsługa w mieście!",
]

DISHES = [
    "pierogi", "żurek", "schabowy", "bigos", "gołąbki", "rosół",
    "tatar", "stek", "łosoś", "kaczka", "barszcz", "naleśniki",
    "sernik", "tiramisu", "burger", "pizza", "pasta", "risotto",
    "placki ziemniaczane", "flaczki", "pyzy", "szarlotka",
]

FIRST_NAMES = [
    "Jan", "Anna", "Piotr", "Maria", "Tomasz", "Katarzyna",
    "Michał", "Agnieszka", "Marcin", "Magdalena", "Paweł", "Joanna",
    "Adam", "Ewa", "Łukasz", "Monika", "Jakub", "Natalia",
]


def _random_dish():
    return random.choice(DISHES)


def _generate_genuine_review(can_mention_staff=False, staff_names=None):
    """Generate a realistic genuine review."""
    if can_mention_staff and staff_names and random.random() < 0.08:
        # ~8% of genuine reviews organically mention staff
        template = random.choice(GENUINE_WITH_STAFF)
        text = template.format(
            staff=random.choice(staff_names),
            dish=_random_dish(),
        )
        depth = random.choice(["moderate", "detailed"])
        specificity = random.randint(2, 4)
    else:
        template = random.choice(GENUINE_TEMPLATES)
        text = template.format(dish=_random_dish(), dish2=_random_dish())
        depth = random.choice(["shallow", "moderate", "moderate", "detailed"])
        specificity = random.randint(1, 5)

    rating = random.choices([5, 4, 3, 2, 1], weights=[35, 30, 15, 10, 10])[0]
    sentiment_map = {5: "positive", 4: "positive", 3: "mixed",
                     2: "negative", 1: "negative"}

    return {
        "text": text,
        "rating": rating,
        "sentiment": sentiment_map[rating],
        "depth": depth,
        "specificity": specificity,
        "author_reviews": random.randint(3, 200),
        "is_fake": False,
    }


def _generate_fake_review(staff_name: str):
    """Generate a fake campaign review."""
    template = random.choice(FAKE_TEMPLATES)
    text = template.format(staff=staff_name)

    return {
        "text": text,
        "rating": 5,
        "sentiment": "positive",
        "depth": "shallow",
        "specificity": random.randint(0, 1),
        "author_reviews": random.randint(1, 4),  # low review count
        "is_fake": True,
        "staff_name": staff_name,
    }


def seed_database():
    """Generate and insert all demo data."""
    init_db()

    with get_db() as conn:
        for rest in DEMO_RESTAURANTS:
            # Insert restaurant
            insert_restaurant(conn, {
                "place_id": rest["place_id"],
                "name": rest["name"],
                "address": rest["address"],
                "rating": rest["rating"],
                "total_reviews": rest["total_reviews"],
                "lat": rest["lat"],
                "lng": rest["lng"],
            })

            # Generate reviews spread over ~18 months
            base_date = datetime(2024, 6, 1)
            review_count = random.randint(150, 250)
            reviews_data = []

            # Generate genuine reviews spread evenly
            for _ in range(review_count):
                days_offset = random.randint(0, 540)  # ~18 months
                dt = base_date + timedelta(
                    days=days_offset,
                    hours=random.randint(10, 22),
                    minutes=random.randint(0, 59),
                )
                rev = _generate_genuine_review(
                    can_mention_staff=rest["has_campaign"],
                    staff_names=rest["campaign_staff"],
                )
                rev["timestamp"] = int(dt.timestamp())
                rev["date"] = dt
                reviews_data.append(rev)

            # Generate fake campaign reviews (clustered in time)
            if rest["has_campaign"]:
                campaign_start = rest["campaign_start"]
                duration = rest["campaign_duration_days"]
                num_fake = random.randint(15, 35)

                for _ in range(num_fake):
                    staff_name = random.choice(rest["campaign_staff"])
                    days_offset = random.randint(0, duration)
                    dt = campaign_start + timedelta(
                        days=days_offset,
                        hours=random.randint(8, 23),
                        minutes=random.randint(0, 59),
                    )
                    rev = _generate_fake_review(staff_name)
                    rev["timestamp"] = int(dt.timestamp())
                    rev["date"] = dt
                    reviews_data.append(rev)

            # Sort by timestamp and insert
            reviews_data.sort(key=lambda x: x["timestamp"])

            for idx, rev in enumerate(reviews_data):
                review_id = hashlib.md5(
                    f"{rest['place_id']}-{idx}-{rev['timestamp']}".encode()
                ).hexdigest()

                author = random.choice(FIRST_NAMES) + " " + chr(random.randint(65, 90)) + "."

                insert_review(conn, {
                    "place_id": rest["place_id"],
                    "review_id": review_id,
                    "author_name": author,
                    "author_url": "",
                    "author_reviews_count": rev["author_reviews"],
                    "rating": rev["rating"],
                    "text": rev["text"],
                    "published_at": rev["date"].isoformat(),
                    "published_timestamp": rev["timestamp"],
                    "language": "pl",
                })

                # Also insert pre-computed analysis
                staff_names = []
                fake_signals = []
                if rev.get("is_fake"):
                    staff_names = [rev["staff_name"]]
                    fake_signals = ["only_mentions_staff", "no_food_details",
                                    "generic_praise", "excessive_exclamation"]
                elif "staff" in rev["text"].lower() or any(
                    name in rev["text"] for name in (rest["campaign_staff"] or [])
                ):
                    # Genuine review that mentions a staff member
                    for name in (rest["campaign_staff"] or []):
                        if name in rev["text"]:
                            staff_names.append(name)

                dishes = []
                for d in DISHES:
                    if d in rev["text"].lower():
                        dishes.append(d)

                # Compute suspicion
                suspicion = 0.0
                if staff_names and not dishes:
                    suspicion += 0.30
                if rev["depth"] == "shallow":
                    suspicion += 0.20
                if rev["author_reviews"] < 5:
                    suspicion += 0.15
                if len(fake_signals) >= 2:
                    suspicion += 0.10
                if rev["specificity"] <= 1:
                    suspicion += 0.05

                insert_analysis(conn, {
                    "review_id": review_id,
                    "place_id": rest["place_id"],
                    "sentiment": rev["sentiment"],
                    "staff_names": staff_names,
                    "dishes_mentioned": dishes,
                    "topics": random.sample(
                        ["service", "food_quality", "ambiance", "price"],
                        k=random.randint(1, 3)
                    ),
                    "review_depth": rev["depth"],
                    "specificity_score": rev["specificity"],
                    "fake_signals": fake_signals,
                    "suspicion_score": min(suspicion, 1.0),
                    "in_burst": 0,
                })

            print(f"  ✅ {rest['name']}: {len(reviews_data)} reviews "
                  f"({'campaign' if rest['has_campaign'] else 'clean'})")

    print(f"\n🎉 Demo database seeded at {DB_PATH}")
    print("   Now run: python detect.py && python app.py --debug")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true",
                        help="Delete existing DB and re-seed")
    args = parser.parse_args()

    if args.clean and DB_PATH.exists():
        os.remove(DB_PATH)
        print("🗑️  Old database removed.")

    seed_database()


if __name__ == "__main__":
    main()
