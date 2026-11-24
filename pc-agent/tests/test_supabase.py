from __future__ import annotations

import unittest
from unittest import mock

from framepulse_agent.supabase import SupabaseClient, SupabaseError, describe_response


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

        client.list_games()

        self.assertEqual(session.calls[0]["url"], f"{url}/games")


if __name__ == "__main__":
    unittest.main()
