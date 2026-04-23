class AllManga:
    @property
    def headers(self) -> dict: return {}

    @property
    def extractor_headers(self) -> dict: return {}

    async def search(self, title: str) -> list[dict]: return []
    async def get_anime_info(self, id: str) -> dict: return {}
    async def get_episode_sources(self, id: str) -> dict: return {}
