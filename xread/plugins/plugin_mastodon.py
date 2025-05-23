from xread.plugins.base import ScraperPlugin
from xread.models import ScrapedData

class MastodonPlugin(ScraperPlugin):
    async def can_handle(self, url: str) -> bool:
        return 'mastodon' in url or '@' in url
    
    async def scrape(self, url: str) -> ScrapedData:
        """
        Scrape a Mastodon post and its replies using the Mastodon API.
        """
        import re
        import aiohttp
        from datetime import datetime

        # Example Mastodon status URL: https://mastodon.social/@user/123456789012345678
        match = re.match(r"https?://([^/]+)/@[^/]+/(\d+)", url)
        if not match:
            raise ValueError("Invalid Mastodon status URL format")
        instance, status_id = match.group(1), match.group(2)
        api_base = f"https://{instance}/api/v1/statuses/{status_id}"

        async with aiohttp.ClientSession() as session:
            # Fetch main status
            async with session.get(api_base) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to fetch Mastodon status: {resp.status}")
                status_json = await resp.json()

            # Fetch context (replies)
            async with session.get(f"{api_base}/context") as resp:
                if resp.status != 200:
                    replies_json = {"descendants": []}
                else:
                    replies_json = await resp.json()

        # Helper to parse a status JSON into a Post
        def parse_post(status) -> 'Post':
            from xread.models import Post, Image
            user = status["account"]["display_name"] or status["account"]["username"]
            username = status["account"]["username"]
            text = status["content"]
            date = status["created_at"]
            permalink = status["url"]
            images = [
                Image(url=media["url"], description=media.get("description"))
                for media in status.get("media_attachments", [])
                if media.get("type") == "image"
            ]
            return Post(
                user=user,
                username=username,
                text=text,
                date=date,
                permalink=permalink,
                images=images,
                status_id=status["id"],
                likes=status.get("favourites_count", 0),
                retweets=status.get("reblogs_count", 0),
                replies_count=status.get("replies_count", 0),
                topic_tags=[tag["name"] for tag in status.get("tags", [])]
            )

        main_post = parse_post(status_json)
        replies = [parse_post(reply) for reply in replies_json.get("descendants", [])]

        return ScrapedData(
            main_post=main_post,
            replies=replies,
            factual_context=None,
            source="mastodon"
        )
