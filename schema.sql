CREATE TABLE IF NOT EXISTS current_products (
    store_slug TEXT NOT NULL,
    ean TEXT NOT NULL,
    product_id TEXT,
    product_name TEXT,
    brand TEXT,
    cat1 TEXT,
    cat2 TEXT,
    cat3 TEXT,
    price NUMERIC,
    list_price NUMERIC,
    stock INTEGER,
    offer_pct NUMERIC,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (store_slug, ean)
);

CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    store_slug TEXT NOT NULL,
    ean TEXT NOT NULL,
    product_id TEXT,
    product_name TEXT,
    brand TEXT,
    cat1 TEXT,
    cat2 TEXT,
    cat3 TEXT,
    price NUMERIC,
    list_price NUMERIC,
    stock INTEGER,
    offer_pct NUMERIC,
    previous_price NUMERIC,
    previous_list_price NUMERIC,
    previous_stock INTEGER,
    delta_price NUMERIC,
    delta_pct NUMERIC,
    change_kind TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_current_products_ean ON current_products (ean);
CREATE INDEX IF NOT EXISTS idx_price_history_ean ON price_history (ean);
CREATE INDEX IF NOT EXISTS idx_price_history_store_captured ON price_history (store_slug, captured_at DESC);
