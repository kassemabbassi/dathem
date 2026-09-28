"""Per-user setup profile helpers for DATHEM Agent V1."""

import hashlib
import hmac
import json
import os
import secrets


APP_DIRECTORY_NAME = "DathemAgentV1"
PROFILE_FILENAME = "profile.json"
PASSWORD_ITERATIONS = 600_000


def user_data_directory():
    """Return the current interactive user's private app-data directory."""
    local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local_app_data, APP_DIRECTORY_NAME)


def profile_path():
    return os.path.join(user_data_directory(), PROFILE_FILENAME)


def make_password_record(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return {
        "password_salt": salt.hex(),
        "password_hash": digest.hex(),
        "password_iterations": PASSWORD_ITERATIONS,
    }


def verify_password(password, profile):
    try:
        salt = bytes.fromhex(profile["password_salt"])
        expected = bytes.fromhex(profile["password_hash"])
        iterations = int(profile["password_iterations"])
    except (KeyError, TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(actual, expected)


def save_profile(profile):
    directory = user_data_directory()
    os.makedirs(directory, exist_ok=True)
    destination = os.path.join(directory, PROFILE_FILENAME)
    temporary = destination + ".tmp"
    with open(temporary, "w", encoding="utf-8") as profile_file:
        json.dump(profile, profile_file, ensure_ascii=False)
    os.replace(temporary, destination)
    return destination


def load_profile():
    path = profile_path()
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as profile_file:
        profile = json.load(profile_file)

    encodings = profile.get("encodings")
    if not isinstance(encodings, list) or not encodings:
        raise ValueError("DATHEM profile has no enrolled face encodings")
    if any(not isinstance(item, list) or len(item) != 128 for item in encodings):
        raise ValueError("DATHEM profile contains an invalid face encoding")
    return profile
