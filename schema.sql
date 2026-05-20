-- Borramos las tablas viejas para liberar los 200MB
DROP TABLE IF EXISTS price_history CASCADE;
DROP TABLE IF EXISTS current_products CASCADE;
DROP TABLE IF EXISTS catalogo_unificado CASCADE;

-- 1. Catálogo Maestro (Solo identificadores, CERO precios o stock)
CREATE TABLE catalogo_unificado (
    ean TEXT PRIMARY KEY,
    product_name TEXT,
    brand TEXT
);

-- 2. Estado Actual (Vinculado al catálogo, guarda la "foto" del momento)
CREATE TABLE current_products (
    store_slug TEXT NOT NULL,
    ean TEXT NOT NULL REFERENCES catalogo_unificado(ean),
    cat1 TEXT,
    cat2 TEXT,
    cat3 TEXT,
    price NUMERIC,
    stock INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (store_slug, ean)
);

-- 3. Historial (Solo guarda cambios reales, sin registro "NEW")
CREATE TABLE price_history (
    id BIGSERIAL PRIMARY KEY,
    store_slug TEXT NOT NULL,
    ean TEXT NOT NULL REFERENCES catalogo_unificado(ean),
    previous_price NUMERIC,
    new_price NUMERIC,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_current_products_ean ON current_products (ean);
CREATE INDEX idx_price_history_ean ON price_history (ean);

-- 4. La Vista para descargar todo junto fácilmente luego
CREATE OR REPLACE VIEW vista_descarga_productos AS
SELECT 
    c.ean, 
    c.product_name, 
    c.brand, 
    p.cat1, 
    p.cat2, 
    p.cat3, 
    p.price, 
    p.updated_at AS fecha_scrapeo, 
    p.store_slug AS plataforma
FROM catalogo_unificado c
JOIN current_products p ON c.ean = p.ean
WHERE p.stock = 1;
