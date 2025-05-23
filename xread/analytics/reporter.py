from dataclasses import dataclass
from typing import List, Dict
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

@dataclass
class ScrapingStats:
    total_posts: int
    success_rate: float
    avg_processing_time: float
    top_sources: List[tuple]
    daily_volume: Dict[str, int]

class AnalyticsReporter:
    def __init__(self, data_manager: AsyncDataManager):
        self.data_manager = data_manager
    
    async def generate_daily_report(self) -> ScrapingStats:
        """Generate comprehensive daily statistics"""
        # Query database for metrics
        posts = await self.data_manager.list_meta(limit=1000)
        
        # Calculate stats
        total_posts = len(posts)
        success_rate = self._calculate_success_rate(posts)
        
        return ScrapingStats(
            total_posts=total_posts,
            success_rate=success_rate,
            avg_processing_time=self._avg_processing_time(posts),
            top_sources=self._top_sources(posts),
            daily_volume=self._daily_volume(posts)
        )
    
    def generate_charts(self, stats: ScrapingStats) -> str:
        """Generate visualization charts"""
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        # Daily volume chart
        dates = list(stats.daily_volume.keys())
        volumes = list(stats.daily_volume.values())
        ax1.plot(dates, volumes)
        ax1.set_title('Daily Scraping Volume')
        
        # Success rate pie chart
        ax2.pie([stats.success_rate, 1-stats.success_rate], 
                labels=['Success', 'Failed'], autopct='%1.1f%%')
        ax2.set_title('Success Rate')
        
        # Top sources bar chart
        sources, counts = zip(*stats.top_sources) if stats.top_sources else ([], [])
        ax3.bar(sources, counts)
        ax3.set_title('Top Sources')
        
        plt.tight_layout()
        chart_path = f"analytics/report_{datetime.now().strftime('%Y%m%d')}.png"
        plt.savefig(chart_path)
        return chart_path
