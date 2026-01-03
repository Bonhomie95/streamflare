import requests
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone



class TwitchClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: Optional[str] = None

    def _get_app_token(self) -> str:
        if self._token:
            return self._token

        url = "https://id.twitch.tv/oauth2/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        r = requests.post(url, data=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        self._token = str(data["access_token"])
        return self._token

   
    def get_top_clips(
    self,
    broadcaster_id: str,
    lookback_hours: int = 48,
    limit: int = 10,
    ):
        started_at = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()

        url = "https://api.twitch.tv/helix/clips"
        params = {
        "broadcaster_id": broadcaster_id,
        "first": limit,
        "started_at": started_at,
        }

        r = requests.get(url, headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("data", [])

    def _headers(self) -> Dict[str, str]:
        token = self._get_app_token()
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
        }

    def get_user(self, user_id: str) -> Dict[str, Any]:
        url = "https://api.twitch.tv/helix/users"
        r = requests.get(
            url, headers=self._headers(), params={"id": user_id}, timeout=30
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        return data[0] if data else {}

    def get_latest_vods(
        self, broadcaster_id: str, limit: int = 5
    ) -> list[Dict[str, Any]]:
        # type=archive returns past broadcasts (VODs)
        url = "https://api.twitch.tv/helix/videos"
        params = {
            "user_id": broadcaster_id,
            "type": "archive",
            "first": limit,
        }
        r = requests.get(url, headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("data", [])

    def get_game(self, game_id: str) -> Dict[str, Any]:
        if not game_id:
            return {}
        url = "https://api.twitch.tv/helix/games"
        r = requests.get(
            url, headers=self._headers(), params={"id": game_id}, timeout=30
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        return data[0] if data else {}
