import os 
import chromadb.config
import logging
from chromadb.telemetry.events import ClientStartEvent
from chromadb.telemetry.posthog import Posthog

logger = logging.getLogger(__name__)

__settings = chromadb.config.Settings()

__version__ = "0.3.21"

def init_webhooks(base_url):
    # Update inbound traffic via APIs to use the public-facing ngrok URL
    pass

def configure(**kwargs):
    """Override Chroma's default settings, environment variables or .env files"""
    global __settings
    __settings = chromadb.config.Settings(**kwargs)


def get_settings():
    return __settings


def get_db(settings=__settings):
    """Return a chroma.DB instance based on the provided or environmental settings."""

    setting = settings.chroma_db_impl.lower()

    def require(key):
        assert settings[key], f"Setting '{key}' is required when chroma_db_impl={setting}"

    if setting == "clickhouse":
        require("clickhouse_host")
        require("clickhouse_port")
        require("persist_directory")
        logger.info("Using Clickhouse for database")
        import chromadb.db.clickhouse

        return chromadb.db.clickhouse.Clickhouse(settings)
    elif setting == "duckdb+parquet":
        require("persist_directory")
        logger.warning(
            f"Using embedded DuckDB with persistence: data will be stored in: {settings.persist_directory}"
        )
        import chromadb.db.duckdb

        return chromadb.db.duckdb.PersistentDuckDB(settings)
    elif setting == "duckdb":
        require("persist_directory")
        logger.warning("Using embedded DuckDB without persistence: data will be transient")
        import chromadb.db.duckdb

        return chromadb.db.duckdb.DuckDB(settings)
    else:
        raise ValueError(
            f"Expected chroma_db_impl to be one of clickhouse, duckdb, duckdb+parquet, got {setting}"
        )


def Client(settings=__settings, username=None, password=None):
    """Return a chroma.API instance based on the provided or environmental
    settings, optionally overriding the DB instance."""

    setting = settings.chroma_api_impl.lower()
    telemetry_client = Posthog(settings)

    # Submit event for client start
    telemetry_client.capture(ClientStartEvent())

    def require(key):
        assert settings[key], f"Setting '{key}' is required when chroma_api_impl={setting}"

    if setting == "rest":
        require("chroma_server_host")
        require("chroma_server_http_port")
        BASE_URL = "http://localhost:8000"
        USE_NGROK = os.environ.get("USE_NGROK", "False") == "True"
        # pyngrok should only ever be installed or initialized in a dev environment when this flag is set
        from pyngrok import ngrok

        # Get the dev server port (defaults to 8000 for Uvicorn, can be overridden with `--port`
        # when starting the server
        port = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else 8000

        # Open a ngrok tunnel to the dev server
        public_url = ngrok.connect(port).public_url
        logger.info("ngrok tunnel \"{}\" -> \"http://127.0.0.1:{}\"".format(public_url, port))

        # Update any base URLs or webhooks to use the public ngrok URL
        settings.BASE_URL = public_url
        init_webhooks(public_url)
        logger.info("Running Chroma in client mode using REST to connect to remote server")
        import chromadb.api.fastapi

        return chromadb.api.fastapi.FastAPI(settings, username, password, telemetry_client)
    elif setting == "local":
        logger.info("Running Chroma using direct local API.")
        import chromadb.api.local

        return chromadb.api.local.LocalAPI(settings, get_db(settings), telemetry_client)
    else:
        raise ValueError(f"Expected chroma_api_impl to be one of rest, local, got {setting}")
