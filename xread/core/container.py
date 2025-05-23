from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject

from xread.data_manager import AsyncDataManager
from xread.ai_models import AIModelFactory
from xread.scraper import ScraperService

class Container(containers.DeclarativeContainer):
    # Configuration
    config = providers.Configuration()
    
    # Database
    database = providers.Singleton(
        AsyncDataManager
    )
    
    # AI Models
    ai_model_factory = providers.Factory(
        AIModelFactory,
        config=config.ai
    )
    
    # Services
    scraper_service = providers.Factory(
        ScraperService,
        database=database,
        ai_model=ai_model_factory
    )
