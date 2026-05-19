import os
from decimal import Decimal
from typing import List, Dict, Any, Tuple

import psycopg2
from psycopg2.extras import execute_values

SCHEMA_SQL = open(
    os.path.join(os.path.dirname(__file__), 'schema.sql'),
    encoding='utf-8'
).read()


def connect_db():
    url = os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('Falta DATABASE_URL. Usá la cadena de conexión de Supabase/Postgres.')
    return psycopg2.connect(
        url,
        sslmode="require"
    )


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def _rows_to_map(rows):
    out = {}
    for row in rows:
        ean = str(row[0]).strip()
        out[ean] = {
            'price': row[1],
            'list_price': row[2],
            'stock': row[3]
        }
    return out


def _normalize_row(r: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(r)
    out['store_slug'] = str(out.get('store_slug', '')).strip()
    out['ean'] = str(out.get('ean', '')).strip()
    return out


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dedup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        nr = _normalize_row(r)
        store_slug = nr.get('store_slug', '')
        ean = nr.get('ean', '')
        if not store_slug or not ean:
            continue
        dedup[(store_slug, ean)] = nr
    return list(dedup.values())


def fetch_existing_current(conn, store_slug: str, eans: List[str]):
    if not eans:
        return {}
    
    eans = [str(e).strip() for e in eans if str(e).strip()]
    if not eans:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            '''
            SELECT ean, price, list_price, stock
            FROM current_products
            WHERE store_slug = %s AND ean = ANY(%s)
            ''',
            (store_slug, eans),
        )
        return _rows_to_map(cur.fetchall())


def upsert_current_and_history(conn, rows: List[Dict[str, Any]]):
    if not rows:
        return {'current_upserted': 0, 'history_inserted': 0}

    rows = _dedupe_rows(rows)

    if not rows:
        return {'current_upserted': 0, 'history_inserted': 0}

    store_slug = rows[0]['store_slug']
    eans = [str(r['ean']).strip() for r in rows if str(r.get('ean', '')).strip()]
    existing = fetch_existing_current(conn, store_slug, eans)

    current_values = []
    history_values = []

    # Helper para convertir de forma segura cualquier número a Decimal
    def _to_decimal(val):
        if val is None or val == '':
            return None
        try:
            return Decimal(str(val))
        except (ValueError, TypeError, Exception):
            return None

    for r in rows:
        ean = str(r.get('ean', '')).strip()
        if not ean:
            continue

        prev = existing.get(ean)

        current_values.append((
            r['store_slug'],
            ean,
            r.get('product_id'),
            r.get('product_name'),
            r.get('brand'),
            r.get('cat1'),
            r.get('cat2'),
            r.get('cat3'),
            r.get('price'),
            r.get('list_price'),
            r.get('stock'),
            r.get('offer_pct')
        ))

        if prev is None:
            history_values.append((
                r['store_slug'],
                ean,
                r.get('product_id'),
                r.get('product_name'),
                r.get('brand'),
                r.get('cat1'),
                r.get('cat2'),
                r.get('cat3'),
                r.get('price'),
                r.get('list_price'),
                r.get('stock'),
                r.get('offer_pct'),
                None,
                None,
                None,
                None,
                None,
                'NEW'
            ))
            continue

        prev_price = prev['price']
        prev_list = prev['list_price']
        prev_stock = prev['stock']

        # Normalizamos los valores nuevos a Decimal
        new_price = _to_decimal(r.get('price'))
        new_list = _to_decimal(r.get('list_price'))
        new_stock = r.get('stock')
        
        # Normalizamos los valores previos de PostgreSQL a Decimal de Python
        prev_price_dec = _to_decimal(prev_price)
        prev_list_dec = _to_decimal(prev_list)

        changed = (
            prev_price_dec != new_price or
            prev_list_dec != new_list or
            prev_stock != new_stock
        )

        if changed:
            delta_price = None
            delta_pct = None

            try:
                if prev_price_dec is not None and new_price is not None:
                    delta_price = new_price - prev_price_dec
                    if prev_price_dec != Decimal('0'):
                        delta_pct = (delta_price / prev_price_dec) * Decimal('100')
            except Exception:
                pass

            history_values.append((
                r['store_slug'],
                ean,
                r.get('product_id'),
                r.get('product_name'),
                r.get('brand'),
                r.get('cat1'),
                r.get('cat2'),
                r.get('cat3'),
                r.get('price'),
                r.get('list_price'),
                r.get('stock'),
                r.get('offer_pct'),
                prev_price,
                prev_list,
                prev_stock,
                delta_price,
                delta_pct,
                'PRICE_CHANGE'
            ))

    with conn.cursor() as cur:
        if current_values:
            execute_values(
                cur,
                '''
                INSERT INTO current_products
                (store_slug, ean, product_id, product_name, brand, cat1, cat2, cat3, price, list_price, stock, offer_pct)
                VALUES %s
                ON CONFLICT (store_slug, ean) DO UPDATE SET
                    product_id = EXCLUDED.product_id,
                    product_name = EXCLUDED.product_name,
                    brand = EXCLUDED.brand,
                    cat1 = EXCLUDED.cat1,
                    cat2 = EXCLUDED.cat2,
                    cat3 = EXCLUDED.cat3,
                    price = EXCLUDED.price,
                    list_price = EXCLUDED.list_price,
                    stock = EXCLUDED.stock,
                    offer_pct = EXCLUDED.offer_pct,
                    updated_at = NOW()
                ''',
                current_values,
                page_size=500,
            )

        if history_values:
            execute_values(
                cur,
                '''
                INSERT INTO price_history
                (store_slug, ean, product_id, product_name, brand, cat1, cat2, cat3, price, list_price, stock, offer_pct,
                 previous_price, previous_list_price, previous_stock, delta_price, delta_pct, change_kind)
                VALUES %s
                ''',
                history_values,
                page_size=500,
            )

    conn.commit()
    return {
        'current_upserted': len(current_values),
        'history_inserted': len(history_values)
    }