import os
from decimal import Decimal
from typing import List, Dict, Any

import psycopg2
from psycopg2.extras import execute_values

SCHEMA_SQL = open(os.path.join(os.path.dirname(__file__), 'schema.sql'), encoding='utf-8').read()


def connect_db():
    url = os.getenv('DATABASE_URL')
    if not url:
        raise RuntimeError('Falta DATABASE_URL. Usá la cadena de conexión de Supabase/Postgres.')
    return psycopg2.connect(url)


def ensure_schema(conn):
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()


def _rows_to_map(rows):
    out = {}
    for row in rows:
        out[row[0]] = {'price': row[1], 'list_price': row[2], 'stock': row[3]}
    return out


def fetch_existing_current(conn, store_slug: str, eans: List[str]):
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

    store_slug = rows[0]['store_slug']
    eans = [r['ean'] for r in rows]
    existing = fetch_existing_current(conn, store_slug, eans)

    current_values = []
    history_values = []

    for r in rows:
        prev = existing.get(r['ean'])
        current_values.append((
            r['store_slug'], r['ean'], r.get('product_id'), r.get('product_name'), r.get('brand'),
            r.get('cat1'), r.get('cat2'), r.get('cat3'), r.get('price'), r.get('list_price'),
            r.get('stock'), r.get('offer_pct')
        ))

        if prev is None:
            history_values.append((
                r['store_slug'], r['ean'], r.get('product_id'), r.get('product_name'), r.get('brand'),
                r.get('cat1'), r.get('cat2'), r.get('cat3'), r.get('price'), r.get('list_price'),
                r.get('stock'), r.get('offer_pct'), None, None, None, None, None, 'NEW'
            ))
            continue

        prev_price = prev['price']
        prev_list = prev['list_price']
        prev_stock = prev['stock']
        changed = (
            prev_price != r.get('price') or
            prev_list != r.get('list_price') or
            prev_stock != r.get('stock')
        )
        if changed:
            delta_price = None
            delta_pct = None
            if prev_price is not None and r.get('price') is not None:
                try:
                    delta_price = Decimal(str(r['price'])) - Decimal(str(prev_price))
                    if prev_price not in (0, '0', None):
                        delta_pct = (delta_price / Decimal(str(prev_price))) * Decimal('100')
                except Exception:
                    pass
            history_values.append((
                r['store_slug'], r['ean'], r.get('product_id'), r.get('product_name'), r.get('brand'),
                r.get('cat1'), r.get('cat2'), r.get('cat3'), r.get('price'), r.get('list_price'),
                r.get('stock'), r.get('offer_pct'), prev_price, prev_list, prev_stock,
                delta_price, delta_pct, 'PRICE_CHANGE'
            ))

    with conn.cursor() as cur:
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
    return {'current_upserted': len(current_values), 'history_inserted': len(history_values)}
