"""Prepare isolated local verification credentials without reading the user's .env."""

import argparse
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8010)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port between 1024 and 65535.')
    destination = Path(__file__).resolve().parents[1] / '.clean-check' / 'container.env'
    destination.parent.mkdir(exist_ok=True)
    try:
        with destination.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(
                f'POSTGRES_PASSWORD={secrets.token_hex(32)}\n'
                f'LEGALLENS_VERIFY_PORT={args.port}\n'
                f'LEGALLENS_ALLOWED_ORIGINS=http://127.0.0.1:{args.port},http://localhost:{args.port}\n'
                'LEGALLENS_SECURE_COOKIES=false\nLEGALLENS_AUTO_MIGRATE=true\n'
                'LEGALLENS_EXPENSIVE_REQUESTS_PER_MINUTE=1000\n'
                'LEGALLENS_MODEL_BASE_URL=\nLEGALLENS_MODEL_API_KEY=\nLEGALLENS_MODEL_NAME=\n'
                'LEGALLENS_EMBEDDING_MODEL=\nLEGALLENS_EMBEDDING_BASE_URL=\nLEGALLENS_EMBEDDING_API_KEY=\n'
            )
        print('Created .clean-check/container.env. Synthetic verification uses local analysis only.')
    except FileExistsError:
        print(
            'Retaining existing .clean-check/container.env so existing verification volumes remain accessible.'
        )


if __name__ == '__main__':
    main()
