import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import types

from app.core.config import Settings


fake_pil = types.ModuleType("PIL")
fake_image_module = types.ModuleType("PIL.Image")
fake_image_module.open = lambda *_args, **_kwargs: None
fake_pil.Image = fake_image_module
sys.modules.setdefault("PIL", fake_pil)
sys.modules.setdefault("PIL.Image", fake_image_module)


def _load_profiles_module():
    module_path = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "profiles.py"
    spec = importlib.util.spec_from_file_location("profiles_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


profiles_module = _load_profiles_module()


class _MissingColumnError(Exception):
    pass


class _FakeUpdateQuery:
    def __init__(self, client, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.payload = None

    def update(self, payload: dict):
        self.payload = dict(payload)
        return self

    def eq(self, _field: str, _value: str):
        return self

    def execute(self):
        self.client.calls.append(
            {
                "table": self.table_name,
                "payload": dict(self.payload or {}),
            }
        )
        if (
            self.client.fail_on_storage_column
            and profiles_module.PROFILE_PICTURE_STORAGE_COLUMN in (self.payload or {})
        ):
            raise _MissingColumnError(
                "Could not find the 'profile_picture_storage_path' column of 'profiles' in the schema cache"
            )
        return SimpleNamespace(data={"ok": True})


class _FakeUpdateClient:
    def __init__(self, *, fail_on_storage_column: bool) -> None:
        self.calls: list[dict] = []
        self.fail_on_storage_column = fail_on_storage_column

    def table(self, table_name: str):
        return _FakeUpdateQuery(self, table_name)


class _FakeSelectQuery:
    def __init__(self, client, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.columns = ""

    def select(self, columns: str):
        self.columns = columns
        return self

    def eq(self, _field: str, _value: str):
        return self

    def single(self):
        return self

    def execute(self):
        self.client.select_calls.append((self.table_name, self.columns))
        if profiles_module.PROFILE_PICTURE_STORAGE_COLUMN in self.columns:
            raise _MissingColumnError(
                "Could not find the 'profile_picture_storage_path' column of 'profiles' in the schema cache"
            )

        return SimpleNamespace(
            data={
                "avatar_url": (
                    "https://example.supabase.co/storage/v1/object/public/"
                    "profile-pictures/user-123/current.png"
                )
            }
        )


class _FakeSelectClient:
    def __init__(self) -> None:
        self.select_calls: list[tuple[str, str]] = []

    def table(self, table_name: str):
        return _FakeSelectQuery(self, table_name)


def test_cors_origins_always_include_frontend_url() -> None:
    settings = Settings(
        app_env="testing",
        app_secret_key="secret",
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon",
        supabase_service_role_key="service",
        supabase_jwt_secret="jwt",
        allowed_origins="https://kazix.vercel.app",
        frontend_url="https://kazixfrontend.vercel.app",
    )

    assert settings.cors_origins == [
        "https://kazix.vercel.app",
        "https://kazixfrontend.vercel.app",
    ]


def test_extract_storage_path_from_avatar_url() -> None:
    storage_path = profiles_module._extract_storage_path_from_avatar_url(
        "https://example.supabase.co/storage/v1/object/public/profile-pictures/user-123/avatar.jpg"
    )

    assert storage_path == "user-123/avatar.jpg"


def test_load_profile_picture_refs_falls_back_to_avatar_url_when_column_is_missing() -> None:
    client = _FakeSelectClient()

    avatar_url, storage_path = profiles_module._load_profile_picture_refs(client, "user-123")

    assert avatar_url == (
        "https://example.supabase.co/storage/v1/object/public/"
        "profile-pictures/user-123/current.png"
    )
    assert storage_path == "user-123/current.png"
    assert client.select_calls == [
        ("profiles", "avatar_url, profile_picture_storage_path"),
        ("profiles", "avatar_url"),
    ]


def test_save_profile_picture_refs_retries_without_storage_column() -> None:
    client = _FakeUpdateClient(fail_on_storage_column=True)

    profiles_module._save_profile_picture_refs(
        client,
        "user-123",
        avatar_url="https://example.supabase.co/storage/v1/object/public/profile-pictures/user-123/new.png",
        storage_path="user-123/new.png",
    )

    assert client.calls == [
        {
            "table": "profiles",
            "payload": {
                "avatar_url": (
                    "https://example.supabase.co/storage/v1/object/public/"
                    "profile-pictures/user-123/new.png"
                ),
                "profile_picture_storage_path": "user-123/new.png",
            },
        },
        {
            "table": "profiles",
            "payload": {
                "avatar_url": (
                    "https://example.supabase.co/storage/v1/object/public/"
                    "profile-pictures/user-123/new.png"
                )
            },
        },
    ]
