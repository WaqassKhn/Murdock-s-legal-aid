import argparse
import getpass
import os
import httpx


def main():
    parser = argparse.ArgumentParser(
        description='Seed clearly labeled LegalLens demo workspaces through the authenticated API.'
    )
    parser.add_argument('command', choices=['seed'])
    parser.add_argument('--url', default=os.getenv('LEGALLENS_APP_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--email', required=True)
    parser.add_argument('--register', action='store_true', help='Create an account instead of signing in')
    args = parser.parse_args()
    password = getpass.getpass('LegalLens password (12+ characters): ')
    with httpx.Client(base_url=args.url, timeout=30) as client:
        result = client.post(
            '/api/auth/' + ('register' if args.register else 'login'),
            json={'email': args.email, 'password': password},
        )
        result.raise_for_status()
        response = client.post('/api/demo')
        response.raise_for_status()
        for workspace in response.json():
            print(f'{workspace["name"]}: {workspace["id"]} (synthetic demo; processing asynchronously)')


if __name__ == '__main__':
    main()
