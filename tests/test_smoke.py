import asyncio
import unittest

from app.db import init_db
from app.main import app
from app.services.story_loader import get_all_stories, load_story_files


class SmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_app_boots_and_story_loader_works(self) -> None:
        await init_db()
        self.assertEqual(app.title, "Interactive Story Bot")

        stories = load_story_files()
        self.assertTrue(isinstance(stories, dict))
        self.assertGreaterEqual(len(stories), 1)

        all_stories = get_all_stories()
        self.assertTrue(isinstance(all_stories, list))
        self.assertGreaterEqual(len(all_stories), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
