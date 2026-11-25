from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from framepulse_agent.config import DEFAULT_CONFIG, load_config
from framepulse_agent.supabase import (
    SupabaseClient,
    SupabaseError,
    derive_neon_auth_url,
    describe_response,
    extract_jwt_from_response,
)


class DescribeResponseTests(unittest.TestCase):
    def test_missing_tables(self) -> None:
        error = describe_response(404, {"code": "PGRST205", "message": "not found"})
        self.assertIn("The tables are not created", str(error))
        self.assertEqual(error.code, "PGRST205")

    def test_missing_tables_by_message(self) -> None:
        error = describe_response(404, {"message": "Could not find table in schema cache"})
        self.assertIn("neon_schema.sql", str(error))

    def test_permission_denied(self) -> None:
        error = describe_response(403, {"code": "42501", "message": "permission denied for table games"})
        self.assertIn("missing grants", str(error))

    def test_bad_key(self) -> None:
        error = describe_response(401, {"message": "Invalid API key"})
        self.assertIn("neon_api_key", str(error))

    def test_pgrst302_mentions_neon_auth(self) -> None:
        error = describe_response(
            401,
            {"code": "PGRST302", "message": "required authorization bearer token in JWT format"},
        )
        self.assertEqual(error.status, 401)
        self.assertEqual(error.code, "PGRST302")
        self.assertIn("Neon Auth", str(error))
        self.assertIn("PGRST302", str(error))

    def test_generic_error(self) -> None:
        error = describe_response(500, {"message": "boom", "details": "detail"})
        self.assertEqual(str(error), "boom")
        self.assertEqual(error.status, 500)
        self.assertEqual(error.details, "detail")

    def test_generic_error_without_message(self) -> None:
        error = describe_response(418, None)
        self.assertIn("418", str(error))

    def test_duplicate_is_recognized(self) -> None:
        from framepulse_agent.supabase import is_duplicate

        error = describe_response(409, {"code": "23505", "message": "duplicate key"})
        self.assertTrue(is_duplicate(error))
        self.assertFalse(is_duplicate(describe_response(400, {"code": "23514"})))


class FakeResponse:
    def __init__(self, status: int = 200, payload=b"[]") -> None:
        self.status_code = status
        self.content = payload
        self.text = payload.decode("utf-8")

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        import json

        return json.loads(self.content)


class FakeSession:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[dict] = []
        self._responses = responses or []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0) if self._responses else FakeResponse()

    def close(self) -> None:
        pass


class SupabaseClientTests(unittest.TestCase):
    def test_urls_headers_and_listing(self) -> None:
        session = FakeSession([FakeResponse(200, b'[{"id":"1","name":"Game","process_name":"game.exe"}]')])
        client = SupabaseClient("https://example.supabase.co/", "key", session=session)

        games = client.list_games()

        self.assertEqual(len(games), 1)
        call = session.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], "https://example.supabase.co/rest/v1/games")
        self.assertEqual(call["params"]["select"], "id,name,process_name")
        self.assertEqual(session.headers["apikey"], "key")
        self.assertEqual(session.headers["Authorization"], "Bearer key")

    def test_create_game_sends_fields(self) -> None:
        session = FakeSession([FakeResponse(201, b'[{"id":"abc"}]')])
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        game = client.create_game("Game", "game.exe")

        self.assertEqual(game["id"], "abc")
        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["headers"]["Prefer"], "return=representation")
        self.assertEqual(call["json"], {"name": "Game", "process_name": "game.exe"})

    def test_create_game_ignores_duplicate(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    409,
                    b'{"code":"23505","message":"duplicate key value violates unique constraint"}',
                )
            ]
        )
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        self.assertIsNone(client.create_game("Game", "game.exe"))

    def test_create_session_ignores_duplicate(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    409,
                    b'{"code":"23505","message":"duplicate key value violates unique constraint"}',
                )
            ]
        )
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        client.create_session(
            session_id="00000000-0000-0000-0000-000000000000",
            game_id="11111111-1111-1111-1111-111111111111",
            played_at="2026-01-01T00:00:00+00:00",
            avg_fps=60.0,
            min_fps=50.0,
            max_fps=70.0,
            duration_seconds=30,
        )

    def test_insert_samples_posts_batch(self) -> None:
        session = FakeSession([FakeResponse(201, b"")])
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        client.insert_samples([{"session_id": "abc", "timestamp_offset": 0.0, "fps": 60.0}])

        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://example.supabase.co/rest/v1/fps_samples")
        self.assertEqual(call["json"][0]["fps"], 60.0)

    def test_insert_samples_posts_telemetry_fields(self) -> None:
        session = FakeSession([FakeResponse(201, b"")])
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        client.insert_samples(
            [
                {
                    "session_id": "abc",
                    "timestamp_offset": 0.0,
                    "fps": 60.0,
                    "gpu_temp": 55.0,
                    "cpu_temp": 61.0,
                    "gpu_load": 12.5,
                    "cpu_load": 30.0,
                }
            ]
        )

        row = session.calls[0]["json"][0]
        self.assertEqual(
            (row["gpu_temp"], row["cpu_temp"], row["gpu_load"], row["cpu_load"]),
            (55.0, 61.0, 12.5, 30.0),
        )

    def test_server_error_is_retried(self) -> None:
        session = FakeSession(
            [FakeResponse(503, b'{"message":"unavailable"}'), FakeResponse(200, b"[]")]
        )
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        with mock.patch.object(SupabaseClient, "_backoff", staticmethod(lambda attempt: None)):
            self.assertEqual(client.list_games(), [])

        self.assertEqual(len(session.calls), 2)

    def test_client_error_is_not_retried(self) -> None:
        session = FakeSession([FakeResponse(400, b'{"message":"bad request"}')])
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        with self.assertRaises(SupabaseError):
            client.list_games()

        self.assertEqual(len(session.calls), 1)

    def test_no_api_key_omits_auth_headers(self) -> None:
        session = FakeSession([FakeResponse(200, b"[]")])
        client = SupabaseClient("https://example.supabase.co", session=session)

        games = client.list_games()

        self.assertEqual(games, [])
        self.assertNotIn("apikey", session.headers)
        self.assertNotIn("Authorization", session.headers)

    def test_neon_url_keeps_rest_v1_suffix(self) -> None:
        session = FakeSession([FakeResponse(200, b"[]")])
        url = "https://ep-example.apirest.eu-central-1.aws.neon.tech/neondb/rest/v1"
        client = SupabaseClient(url, session=session)

        with mock.patch("urllib.request.urlopen", return_value=_FakeUrlopenResponse(b'{"token":"eyJ.anon.jwt"}')):
            client.list_games()

        self.assertEqual(session.calls[0]["url"], f"{url}/games")
        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer eyJ.anon.jwt")


class _FakeUrlopenResponse:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._stream = io.BytesIO(body)
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._stream.read()

    def __enter__(self) -> _FakeUrlopenResponse:
        return self

    def __exit__(self, *_args) -> None:
        return None


def _make_jwt(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode("ascii").rstrip("=")
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": "anon", "exp": exp}).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    return f"{header}.{payload}.sig"


class NeonAuthDerivationAndConfigTests(unittest.TestCase):
    def test_derives_neon_auth_url_from_data_api_url(self) -> None:
        data_url = "https://ep-dark-base-bhm8rvp5.apirest.c-10.eu-central-1.aws.neon.tech/neondb/rest/v1"
        self.assertEqual(
            derive_neon_auth_url(data_url),
            "https://ep-dark-base-bhm8rvp5.neonauth.c-10.eu-central-1.aws.neon.tech/neondb/auth",
        )
        self.assertEqual(
            derive_neon_auth_url(f"{data_url}/"),
            "https://ep-dark-base-bhm8rvp5.neonauth.c-10.eu-central-1.aws.neon.tech/neondb/auth",
        )

    def test_explicit_neon_auth_url_wins(self) -> None:
        data_url = "https://ep-dark-base-bhm8rvp5.apirest.c-10.eu-central-1.aws.neon.tech/neondb/rest/v1"
        self.assertEqual(
            derive_neon_auth_url(data_url, "https://auth.example.com/custom/"),
            "https://auth.example.com/custom",
        )

    def test_non_neon_url_returns_empty_auth_url(self) -> None:
        self.assertEqual(derive_neon_auth_url("https://example.supabase.co/rest/v1"), "")

    def test_config_defaults_and_neon_auth_url(self) -> None:
        self.assertEqual(
            DEFAULT_CONFIG["neon_url"],
            "https://ep-dark-base-bhm8rvp5.apirest.c-10.eu-central-1.aws.neon.tech/neondb/rest/v1",
        )
        self.assertEqual(DEFAULT_CONFIG["neon_auth_url"], "")

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg_path.write_text(
                json.dumps({"neon_auth_url": "https://auth.example.com/neondb/auth/"}),
                encoding="utf-8",
            )
            cfg = load_config(cfg_path)
            self.assertEqual(cfg.neon_url, DEFAULT_CONFIG["neon_url"])
            self.assertEqual(cfg.neon_auth_url, "https://auth.example.com/neondb/auth")


class NeonAnonymousJwtTests(unittest.TestCase):
    DATA_URL = "https://ep-dark-base-bhm8rvp5.apirest.c-10.eu-central-1.aws.neon.tech/neondb/rest/v1"
    AUTH_TOKEN_URL = (
        "https://ep-dark-base-bhm8rvp5.neonauth.c-10.eu-central-1.aws.neon.tech"
        "/neondb/auth/token/anonymous"
    )

    def test_extracts_jwt_from_supported_shapes(self) -> None:
        self.assertEqual(extract_jwt_from_response(b'{"token":"jwt-1"}'), "jwt-1")
        self.assertEqual(extract_jwt_from_response(b'{"access_token":"jwt-2"}'), "jwt-2")
        self.assertEqual(extract_jwt_from_response(b'{"data":{"token":"jwt-3"}}'), "jwt-3")
        self.assertEqual(
            extract_jwt_from_response(b"{}", {"Set-Auth-Jwt": "jwt-4"}),
            "jwt-4",
        )

    def test_fetches_anonymous_jwt_and_caches_it(self) -> None:
        session = FakeSession([FakeResponse(200, b"[]"), FakeResponse(200, b"[]")])
        client = SupabaseClient(self.DATA_URL, session=session)
        requests_made: list[tuple[str, dict[str, str]]] = []

        def fake_urlopen(req, timeout=20.0):
            requests_made.append((req.full_url, dict(req.header_items())))
            return _FakeUrlopenResponse(b'{"token":"eyJ.cached.jwt"}')

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client.list_games()
            client.list_games()

        self.assertEqual(len(requests_made), 1)
        self.assertEqual(requests_made[0][0], self.AUTH_TOKEN_URL)
        self.assertEqual(requests_made[0][1].get("Accept"), "application/json")
        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer eyJ.cached.jwt")
        self.assertEqual(session.calls[1]["headers"]["Authorization"], "Bearer eyJ.cached.jwt")

    def test_refreshes_expired_anonymous_jwt(self) -> None:
        session = FakeSession([FakeResponse(200, b"[]"), FakeResponse(200, b"[]")])
        client = SupabaseClient(self.DATA_URL, session=session, token_ttl=600.0)
        tokens = iter(["eyJ.first.jwt", "eyJ.second.jwt"])

        def fake_urlopen(_req, timeout=20.0):
            return _FakeUrlopenResponse(json.dumps({"token": next(tokens)}).encode("utf-8"))

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), mock.patch(
            "framepulse_agent.supabase.time.monotonic",
            side_effect=[100.0, 100.0, 750.0, 750.0],
        ):
            client.list_games()
            client.list_games()

        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer eyJ.first.jwt")
        self.assertEqual(session.calls[1]["headers"]["Authorization"], "Bearer eyJ.second.jwt")

    def test_static_jwt_in_api_key_skips_anonymous_fetch(self) -> None:
        session = FakeSession([FakeResponse(200, b"[]")])
        static_jwt = _make_jwt(4_000_000_000)
        client = SupabaseClient(self.DATA_URL, static_jwt, session=session)

        with mock.patch("urllib.request.urlopen") as urlopen_mock:
            client.list_games()

        urlopen_mock.assert_not_called()
        self.assertEqual(session.headers["Authorization"], f"Bearer {static_jwt}")

    def test_refreshes_and_retries_on_http_401_pgrst302(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    401,
                    b'{"code":"PGRST302","message":"required authorization bearer token in JWT format"}',
                ),
                FakeResponse(200, b'[{"id":"1","name":"Game","process_name":"game.exe"}]'),
            ]
        )
        client = SupabaseClient(self.DATA_URL, session=session)
        tokens = iter(["eyJ.stale.jwt", "eyJ.fresh.jwt"])

        def fake_urlopen(_req, timeout=20.0):
            return _FakeUrlopenResponse(
                b"",
                headers={"set-auth-jwt": next(tokens)},
            )

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen) as urlopen_mock:
            games = client.list_games()

        self.assertEqual(len(games), 1)
        self.assertEqual(urlopen_mock.call_count, 2)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer eyJ.stale.jwt")
        self.assertEqual(session.calls[1]["headers"]["Authorization"], "Bearer eyJ.fresh.jwt")

    def test_raises_if_retry_after_401_still_fails(self) -> None:
        err_body = b'{"code":"PGRST302","message":"required authorization bearer token in JWT format"}'
        session = FakeSession([FakeResponse(401, err_body), FakeResponse(401, err_body)])
        client = SupabaseClient(self.DATA_URL, session=session)

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=lambda *_a, **_kw: _FakeUrlopenResponse(
                b'{"data":{"token":"eyJ.rejected.jwt"}}'
            ),
        ) as urlopen_mock:
            with self.assertRaises(SupabaseError) as ctx:
                client.list_games()

        self.assertEqual(urlopen_mock.call_count, 2)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(ctx.exception.code, "PGRST302")
        self.assertIn("Neon Auth", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
