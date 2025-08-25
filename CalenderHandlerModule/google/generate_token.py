from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/calendar']

def main():
    # Get the project root (two levels up from this script)
    project_root = Path(__file__).resolve().parents[1]

    # Build paths dynamically
    credentials_path = project_root / 'google' / 'credentials.json'
    token_path = project_root / 'google' / 'token.json'

    # Run OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token
    with token_path.open('w') as token_file:
        token_file.write(creds.to_json())

    print(f"token.json generated successfully at: {token_path}")

if __name__ == '__main__':
    main()
