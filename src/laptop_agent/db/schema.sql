CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    brand TEXT NOT NULL,
    series TEXT NOT NULL,
    category TEXT NOT NULL,
    cpu TEXT NOT NULL,
    gpu TEXT NOT NULL,
    ram_gb INTEGER NOT NULL,
    storage_gb INTEGER NOT NULL,
    screen_inch REAL NOT NULL,
    resolution TEXT NOT NULL,
    panel TEXT NOT NULL,
    refresh_hz INTEGER NOT NULL,
    weight_kg REAL NOT NULL,
    battery_hours REAL NOT NULL,
    os TEXT NOT NULL,
    price_usd REAL NOT NULL CHECK (price_usd > 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    release_year INTEGER NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    preferences TEXT NOT NULL DEFAULT '{}'   -- long-term memory (JSON)
);

CREATE TABLE IF NOT EXISTS cart_items (
    user_id TEXT NOT NULL REFERENCES users(id),
    product_id TEXT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 5),
    PRIMARY KEY (user_id, product_id)
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL,                     -- placed | shipped | delivered | cancelled
    total_usd REAL NOT NULL,
    shipping_option TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id TEXT NOT NULL REFERENCES orders(id),
    product_id TEXT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price_usd REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_cat_price ON products(category, price_usd);
CREATE INDEX IF NOT EXISTS idx_reviews_product ON reviews(product_id);
