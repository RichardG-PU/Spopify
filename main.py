from flask import Flask, request, redirect
import os
import base64
from requests import post, get
import json
import random
import string
from urllib.parse import urlencode

app = Flask(__name__)

client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
redirect_uri = "http://127.0.0.1:5000/callback"

token = None
data_folder = "data"
json_filename = "likes.json"
dupes_filename = "dupes.json"

if not os.path.exists(data_folder):
    os.makedirs(data_folder)


def generateRandomString(length):
    letters_and_digits = string.ascii_letters + string.digits
    return "".join(random.choice(letters_and_digits) for _ in range(length))


def get_auth_header(token):
    return {"Authorization": "Bearer " + token}


def add_tracks_to_playlist(playlist_id, tracks):
    global token
    if token is None:
        print("Token is not available. Please authorize first.")
        return

    add_tracks_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    add_tracks_headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    }

    chunk_size = 100
    for i in range(0, len(tracks), chunk_size):
        chunk = tracks[i : i + chunk_size]

        uris = [f"spotify:track:{track['track_id']}" for track in chunk]
        add_tracks_body = {"uris": uris, "position": 0}

        add_tracks_response = post(
            add_tracks_url,
            headers=add_tracks_headers,
            data=json.dumps(add_tracks_body),
        )

        if add_tracks_response.status_code == 201:
            print(f"Tracks added to the playlist successfully.")
        else:
            print(
                f"Failed to add tracks to the playlist. Status Code: {add_tracks_response.status_code}"
            )


def create_playlist(playlist_name, playlist_description, is_public=True):
    global token
    user_id = get_user_id()

    if user_id is None:
        print("User ID is not available. Please check your authorization.")
        return None

    create_playlist_url = f"https://api.spotify.com/v1/users/{user_id}/playlists"
    create_playlist_headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    }

    create_playlist_body = {
        "name": playlist_name,
        "description": playlist_description,
        "public": is_public,
    }

    create_playlist_response = post(
        create_playlist_url,
        headers=create_playlist_headers,
        data=json.dumps(create_playlist_body),
    )

    if create_playlist_response.status_code == 201:
        playlist_info = json.loads(create_playlist_response.content)
        playlist_id = playlist_info.get("id")
        print(f"Playlist '{playlist_name}' created successfully with ID: {playlist_id}")
        return playlist_id
    else:
        print(
            f"Failed to create playlist. Status Code: {create_playlist_response.status_code}"
        )
        return None


def get_user_id():
    global token
    if token is None:
        print("Token is not available. Please authorize first.")
        return None

    user_info_url = "https://api.spotify.com/v1/me"
    user_info_headers = get_auth_header(token)
    user_info_response = get(user_info_url, headers=user_info_headers)
    user_info = json.loads(user_info_response.content)
    user_id = user_info.get("id")

    return user_id


def get_likes():
    global token
    if token is None:
        print("Token is not available. Please authorize first.")
        return

    url = "https://api.spotify.com/v1/me/tracks"
    headers = get_auth_header(token)

    limit = 50
    offset = 0
    total_items = float("inf")

    likes_data = []

    while offset < total_items:
        params = {"offset": offset, "limit": limit}

        result = get(url, headers=headers, params=params)

        try:
            json_result = json.loads(result.content)
        except json.decoder.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            print(f"Problematic content: {result.content}")
            return

        if "items" not in json_result:
            print("Unexpected response format. Unable to retrieve liked tracks.")
            return

        total_items = json_result.get("total", 0)

        for item in json_result["items"]:
            track_id = item.get("track", {}).get("id")
            track_name = item.get("track", {}).get("name")
            artist_name = item.get("track", {}).get("artists", [{}])[0].get("name")

            likes_data.append(
                {
                    "track_id": track_id,
                    "track_name": track_name,
                    "artist_name": artist_name,
                }
            )

        offset += limit

    json_filepath = os.path.join(data_folder, json_filename)
    with open(json_filepath, "w") as json_file:
        json.dump(likes_data, json_file, indent=2)

    print(f"Data saved to {json_filepath}")

    track_names = [item["track_name"] for item in likes_data]
    duplicate_names = set(name for name in track_names if track_names.count(name) > 1)

    dupes_filepath = os.path.join(data_folder, dupes_filename)
    with open(dupes_filepath, "w") as dupes_file:
        json.dump(list(duplicate_names), dupes_file, indent=2)

    print(f"Duplicates saved to {dupes_filepath}")

    return likes_data


@app.route("/login")
def login():
    state = generateRandomString(16)
    scope = "user-read-private user-read-email user-library-read playlist-modify-public playlist-modify-private playlist-modify-public playlist-modify-private"

    return redirect(
        "https://accounts.spotify.com/authorize?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "scope": scope,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
    )


@app.route("/callback")
def callback():
    global token
    code = request.args.get("code", None)
    state = request.args.get("state", None)

    if state is None:
        return redirect("/#" + urlencode({"error": "state_mismatch"}))
    else:
        auth_options = {
            "url": "https://accounts.spotify.com/api/token",
            "form": {
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            "headers": {
                "content-type": "application/x-www-form-urlencoded",
                "Authorization": "Basic "
                + base64.b64encode(
                    bytes(f"{client_id}:{client_secret}", "utf-8")
                ).decode("utf-8"),
            },
            "json": True,
        }

        response = post(
            auth_options["url"],
            data=auth_options["form"],
            headers=auth_options["headers"],
        )

        token_response = json.loads(response.text)
        token = token_response.get("access_token")

        likes_data = get_likes()

        playlist_name = "My Liked Tracks"
        playlist_description = "A playlist containing my liked tracks on Spotify"
        is_public = True

        playlist_id = create_playlist(playlist_name, playlist_description, is_public)

        if playlist_id:
            add_tracks_to_playlist(playlist_id, likes_data)

        return "Token received successfully. Playlist created and tracks added. You can now close this window."


if __name__ == "__main__":
    app.run(debug=True)
