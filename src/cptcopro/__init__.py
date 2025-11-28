import asyncio
import sys
import os
import time
import atexit
import re
from selectolax.parser import HTMLParser
import cptcopro.Parsing_Charge_Copro as pcc
import cptcopro.Traitement_Charge_Copro as tp
import cptcopro.Data_To_BDD as dtb
import cptcopro.Backup_DB as bdb
import cptcopro.Parsing_Lots_Copro as pcl
import cptcopro.Traitement_Lots_Copro as tlc
import cptcopro.Dedoublonnage as doublon
import cptcopro.utils.streamlit_launcher as usl
from loguru import logger
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from selectolax.parser import HTMLParser  # type: ignore
from datetime import datetime
from typing import Any
from rich.console import Console
from rich.table import Table
from pathlib import Path
