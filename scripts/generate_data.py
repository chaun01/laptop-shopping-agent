"""Generate a deterministic synthetic laptop catalog + customer reviews.

Data is synthetic (fictional model names, seeded RNG) so that the eval set has a
known ground truth and the project carries no licensing / privacy concerns.

Usage: python scripts/generate_data.py
Outputs: data/processed/products.json, data/processed/reviews.json
"""
import json
import random
from pathlib import Path

SEED = 42
N_PRODUCTS = 200
OUT = Path(__file__).resolve().parents[1] / "data" / "processed"

BRANDS = {
    "Dell": ["Inspira", "Latitude X", "XPSion", "Alien G"],
    "HP": ["Pavilion Neo", "EliteNote", "Spectra", "Omen Pro"],
    "Lenovo": ["IdeaBook", "ThinkEdge", "Yoga Flex", "Legend"],
    "Asus": ["VivoNote", "ZenLite", "ProArt Studio", "ROG Strike"],
    "Acer": ["Aspire Go", "Swift Air", "TravelPro", "Predator X"],
    "Apple": ["MacBook Air", "MacBook Pro"],
    "MSI": ["Modern", "Prestige", "Katana", "Raider"],
}

CATEGORIES = {
    # category: cpu pool, gpu pool, ram, storage, screen, weight range, battery range, base price
    "student": dict(
        cpu=["Intel Core i3-1315U", "Intel Core i5-1335U", "AMD Ryzen 5 7530U", "AMD Ryzen 3 7320U"],
        gpu=["Integrated"], ram=[8, 8, 16], storage=[256, 512], screen=[14.0, 15.6],
        weight=(1.4, 1.9), battery=(6, 10), base=380),
    "ultrabook": dict(
        cpu=["Intel Core Ultra 5 125U", "Intel Core Ultra 7 155U", "AMD Ryzen 7 8840U", "Snapdragon X Plus"],
        gpu=["Integrated"], ram=[16, 16, 32], storage=[512, 1024], screen=[13.3, 13.5, 14.0],
        weight=(0.95, 1.35), battery=(11, 20), base=850),
    "business": dict(
        cpu=["Intel Core Ultra 5 135U", "Intel Core Ultra 7 165U", "AMD Ryzen 7 PRO 8840U"],
        gpu=["Integrated"], ram=[16, 32], storage=[512, 1024], screen=[14.0, 15.6],
        weight=(1.2, 1.7), battery=(10, 16), base=950),
    "gaming": dict(
        cpu=["Intel Core i7-14650HX", "Intel Core i9-14900HX", "AMD Ryzen 7 8845HS", "AMD Ryzen 9 8945HS"],
        gpu=["NVIDIA RTX 4050", "NVIDIA RTX 4060", "NVIDIA RTX 4070", "NVIDIA RTX 4080"],
        ram=[16, 32], storage=[512, 1024, 2048], screen=[15.6, 16.0, 17.3],
        weight=(2.1, 3.0), battery=(3, 7), base=1000),
    "creator": dict(
        cpu=["Intel Core Ultra 9 185H", "AMD Ryzen 9 8945HS", "Intel Core i7-13700H"],
        gpu=["NVIDIA RTX 4060", "NVIDIA RTX 4070"], ram=[32, 64], storage=[1024, 2048],
        screen=[14.5, 16.0], weight=(1.6, 2.2), battery=(7, 12), base=1500),
    "2-in-1": dict(
        cpu=["Intel Core i5-1335U", "Intel Core Ultra 5 125U", "AMD Ryzen 5 7640U"],
        gpu=["Integrated"], ram=[8, 16], storage=[256, 512], screen=[13.3, 14.0],
        weight=(1.2, 1.6), battery=(8, 13), base=650),
}

BRAND_CATEGORY_SERIES = {
    # map a category to the series names that fit it, per brand
    "student": {"Dell": "Inspira", "HP": "Pavilion Neo", "Lenovo": "IdeaBook", "Asus": "VivoNote",
                "Acer": "Aspire Go", "MSI": "Modern"},
    "ultrabook": {"Dell": "XPSion", "HP": "Spectra", "Lenovo": "Yoga Flex", "Asus": "ZenLite",
                  "Acer": "Swift Air", "Apple": "MacBook Air", "MSI": "Prestige"},
    "business": {"Dell": "Latitude X", "HP": "EliteNote", "Lenovo": "ThinkEdge", "Acer": "TravelPro"},
    "gaming": {"Dell": "Alien G", "HP": "Omen Pro", "Lenovo": "Legend", "Asus": "ROG Strike",
               "Acer": "Predator X", "MSI": "Katana"},
    "creator": {"Asus": "ProArt Studio", "Apple": "MacBook Pro", "MSI": "Raider", "Dell": "XPSion"},
    "2-in-1": {"Lenovo": "Yoga Flex", "HP": "Spectra", "Asus": "VivoNote", "Dell": "Inspira"},
}

APPLE_CPU = {"ultrabook": ["Apple M3", "Apple M4"], "creator": ["Apple M4 Pro", "Apple M4 Max"]}
GPU_PRICE = {"Integrated": 0, "NVIDIA RTX 4050": 150, "NVIDIA RTX 4060": 300,
             "NVIDIA RTX 4070": 550, "NVIDIA RTX 4080": 1000}

POS = {
    "battery": "Battery easily lasts my whole work day, I rarely carry the charger.",
    "light": "Very light, I carry it to campus every day without noticing.",
    "screen": "The display is sharp and bright, great for movies and photo editing.",
    "perf": "Performance is excellent, handles heavy multitasking without slowing down.",
    "gaming": "Runs modern AAA games at high settings with smooth frame rates.",
    "value": "Great value for the price, does everything I need for school.",
    "keyboard": "The keyboard is comfortable for long typing sessions.",
    "build": "Build quality feels premium and solid.",
}
NEG = {
    "battery": "Battery life is disappointing, I need to plug in after a few hours.",
    "heavy": "It's heavy and bulky, not great for carrying around.",
    "fan": "Fans get loud under load and the chassis runs hot.",
    "ram": "8GB RAM feels limiting with many browser tabs open.",
    "storage": "Storage fills up quickly, I had to buy an external drive.",
    "price": "A bit expensive for what you get.",
    "screen": "Screen is dim outdoors and colors look washed out.",
}


def make_product(i: int, rng: random.Random) -> dict:
    category = rng.choice(list(CATEGORIES))
    spec = CATEGORIES[category]
    brand = rng.choice(list(BRAND_CATEGORY_SERIES[category]))
    series = BRAND_CATEGORY_SERIES[category][brand]
    cpu = rng.choice(APPLE_CPU.get(category, spec["cpu"])) if brand == "Apple" else rng.choice(spec["cpu"])
    gpu = "Integrated" if brand == "Apple" else rng.choice(spec["gpu"])
    ram = rng.choice(spec["ram"])
    storage = rng.choice(spec["storage"])
    screen = rng.choice(spec["screen"])
    weight = round(rng.uniform(*spec["weight"]), 2)
    battery = round(rng.uniform(*spec["battery"]), 1)
    if brand == "Apple":
        battery = round(battery + 4, 1)
    refresh = rng.choice([144, 165, 240]) if category == "gaming" else rng.choice([60, 60, 90, 120])
    resolution = rng.choice(["1920x1080", "1920x1200"]) if category in ("student", "gaming") \
        else rng.choice(["1920x1200", "2560x1600", "2880x1800"])
    panel = rng.choice(["IPS", "OLED"]) if category in ("ultrabook", "creator") else "IPS"
    os_name = "macOS" if brand == "Apple" else "Windows 11"

    price = spec["base"] + GPU_PRICE[gpu] + (ram - 8) * 12 + (storage - 256) * 0.15
    price += 120 if panel == "OLED" else 0
    price += 250 if brand == "Apple" else 0
    price *= rng.uniform(0.9, 1.15)
    price = int(round(price / 10) * 10 - 1)

    model_no = f"{rng.randint(13, 17)}{rng.choice('ABCDEGX')}{rng.randint(10, 99)}"
    name = f"{brand} {series} {model_no}"
    stock = rng.choice([0, 0, 2, 5, 8, 12, 20, 35])
    return {
        "id": f"LP{i:03d}", "name": name, "brand": brand, "series": series, "category": category,
        "cpu": cpu, "gpu": gpu, "ram_gb": ram, "storage_gb": storage, "screen_inch": screen,
        "resolution": resolution, "panel": panel, "refresh_hz": refresh, "weight_kg": weight,
        "battery_hours": battery, "os": os_name, "price_usd": price, "stock": stock,
        "release_year": rng.choice([2024, 2025, 2025, 2026]),
    }


def describe(p: dict) -> str:
    gpu_txt = "integrated graphics" if p["gpu"] == "Integrated" else f"a dedicated {p['gpu']} GPU"
    return (f"The {p['name']} is a {p['category']} laptop with a {p['cpu']} processor, {gpu_txt}, "
            f"{p['ram_gb']}GB RAM and {p['storage_gb']}GB SSD. It has a {p['screen_inch']}-inch "
            f"{p['resolution']} {p['panel']} {p['refresh_hz']}Hz display, weighs {p['weight_kg']} kg and "
            f"offers about {p['battery_hours']} hours of battery life. Runs {p['os']}.")


def make_reviews(p: dict, rng: random.Random, start_id: int) -> list[dict]:
    pros, cons = [], []
    if p["battery_hours"] >= 11: pros.append("battery")
    if p["battery_hours"] <= 6: cons.append("battery")
    if p["weight_kg"] <= 1.3: pros.append("light")
    if p["weight_kg"] >= 2.3: cons.append("heavy")
    if p["panel"] == "OLED" or p["resolution"] != "1920x1080": pros.append("screen")
    if p["category"] in ("gaming", "creator"): pros.append("perf"); cons.append("fan")
    if p["gpu"] in ("NVIDIA RTX 4060", "NVIDIA RTX 4070", "NVIDIA RTX 4080"): pros.append("gaming")
    if p["price_usd"] < 700: pros.append("value")
    if p["price_usd"] > 1800: cons.append("price")
    if p["ram_gb"] == 8: cons.append("ram")
    if p["storage_gb"] == 256: cons.append("storage")
    if p["category"] == "business": pros += ["keyboard", "build"]
    if not pros: pros.append("keyboard")

    reviews = []
    for k in range(rng.randint(2, 4)):
        pick_pos = rng.sample(pros, k=min(len(pros), rng.randint(1, 2)))
        pick_neg = rng.sample(cons, k=min(len(cons), rng.randint(0, 1))) if cons else []
        rating = max(1, min(5, 3 + len(pick_pos) - len(pick_neg) + rng.choice([-1, 0, 0, 1])))
        text = " ".join([POS[x] for x in pick_pos] + [NEG[x] for x in pick_neg])
        reviews.append({"id": f"RV{start_id + k:04d}", "product_id": p["id"], "rating": rating,
                        "text": text, "aspects_pos": pick_pos, "aspects_neg": pick_neg})
    return reviews


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    products, reviews = [], []
    for i in range(1, N_PRODUCTS + 1):
        p = make_product(i, rng)
        p["description"] = describe(p)
        products.append(p)
        reviews += make_reviews(p, rng, start_id=len(reviews) + 1)
    (OUT / "products.json").write_text(json.dumps(products, indent=2))
    (OUT / "reviews.json").write_text(json.dumps(reviews, indent=2))
    cats = {}
    for p in products:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    print(f"products={len(products)} reviews={len(reviews)} categories={cats}")
    print(f"price range: {min(p['price_usd'] for p in products)}-{max(p['price_usd'] for p in products)} USD")


if __name__ == "__main__":
    main()
