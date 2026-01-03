from .youtube_uploader import get_authenticated_service

if __name__ == "__main__":
    print("🔐 Starting YouTube OAuth flow...")
    yt = get_authenticated_service()
    print("✅ Authentication complete. Token saved.")
