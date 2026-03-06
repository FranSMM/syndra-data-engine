import sys
import os

# To allow Scrapy spiders to import from the main FastAPI app (like app.schemas...)
# We need to add the parent directory of 'app' to the Python path.
# Inside the Docker container, the backend root is '/code'
# Locally, it's the 'backend' folder.

current_dir = os.path.dirname(os.path.abspath(__file__))
# current_dir is backend/app/scraper/scraper
# We want to add backend/
backend_dir = os.path.abspath(os.path.join(current_dir, "../../../"))

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
