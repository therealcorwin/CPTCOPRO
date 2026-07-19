from pcloud_sdk import PCloudSDK, PCloudException
from loguru import logger
import sys
from cptcopro.utils.paths import get_log_path
from cptcopro.utils.env_loader import get_pcloud_credentials, get_pcloud_backup_config


# Charger les credentials OAuth2 pCloud depuis le fichier .env
pcloud_credentials = get_pcloud_credentials()
PCloud_APP_KEY = pcloud_credentials["pcloud_APP_KEY"]
PCloud_APP_SECRET = pcloud_credentials["pcloud_APP_SECRET"]
PCLOUD_BACKUP_CONFIG = get_pcloud_backup_config()

# Configurer les logs avec le bon chemin
LOG_PATH = str(get_log_path("app.log"))

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | <cyan>{extra[type_log]}</cyan> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>|  "
    "<level>{message}</level>",
    level="INFO",
    colorize=True,
)
logger.add(
    LOG_PATH,
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra[type_log]} |{name}: {function}: {line} |  {message}",
    level="INFO",
    rotation="10 MB",
    retention="1 month",
    compression="zip",
)


# Initialize with OAuth2 credentials
sdk = PCloudSDK(
    app_key=PCloud_APP_KEY,
    app_secret=PCloud_APP_SECRET,
    auth_type="oauth2",
    token_manager=True
)

# Step 1: Get authorization URL
redirect_uri = "http://localhost:8000/callback"
auth_url = sdk.get_auth_url(redirect_uri)

print(f"Please visit this URL to authorize the application:")
print(auth_url)

# User visits URL, authorizes app, gets redirected with code
# Extract 'code' parameter from callback URL

# Step 2: Exchange code for access token
try:
    authorization_code = input("Enter authorization code: ")
    token_info = sdk.authenticate(
        authorization_code,
        location_id=PCLOUD_BACKUP_CONFIG["pcloud_location_id"],
    )

    print(f" Authentication successful!")
    print(f"Access Token: {token_info['access_token']}")
    print(f"Location: {token_info['locationid']}")

except PCloudException as e:
    print(f"L Authentication failed: {e}")
