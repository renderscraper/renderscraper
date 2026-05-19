import argparse
import os
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scraper import discover_configs, run_store
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = pathlib.Path(__file__).parent.resolve()


def parse_args():
    parser = argparse.ArgumentParser(description='Pipeline listo para Render y Supabase/Postgres')
    sub = parser.add_subparsers(dest='command', required=True)

    s = sub.add_parser('serve', help='Servidor mínimo de salud')
    s.add_argument('--port', type=int, default=int(os.getenv('PORT', '10000')))

    run = sub.add_parser('run', help='Ejecuta todos los scrapers detectados')
    run.add_argument('--only', nargs='*', help='Lista de store_slug a ejecutar')

    return parser.parse_args()


def serve(port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ('/', '/healthz'):
                body = b'OK'
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            return

    print(f'Health server on port {port}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()


async def _run_all(only=None):
    configs = discover_configs(BASE_DIR)
    if only:
        only = {x.strip().lower() for x in only}
        configs = [c for c in configs if c[0].lower() in only]
    if not configs:
        print('No se encontraron config_*.py para ejecutar', flush=True)
        return 1

    for store_slug, module_name in configs:
        print(f'\n=== {store_slug.upper()} ===', flush=True)
        await run_store(store_slug, module_name)
    return 0


def main():
    args = parse_args()
    if args.command == 'serve':
        serve(args.port)
        return
    if args.command == 'run':
        import asyncio
        raise SystemExit(asyncio.run(_run_all(args.only)))


if __name__ == '__main__':
    main()
