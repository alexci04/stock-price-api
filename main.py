from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, LXMLWebScrapingStrategy
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
import json
import logging
from logging.handlers import RotatingFileHandler
import uvicorn
import os

# Set up structured logging with rotation
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
handler = RotatingFileHandler("api.log", maxBytes=10_000_000, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# Initialize FastAPI app with metadata
app = FastAPI(
    title="Real-Time Stock Price API",
    description="Fetch real-time stock prices from Yahoo Finance with near unlimited requests. ~5-second latency. Ideal for portfolio tracking, research, or educational use. Not suitable for high-frequency trading.",
    version="1.0.0",
    docs_url="/docs",
    openapi_tags=[
        {
            "name": "Stock Prices",
            "description": "Endpoints to fetch stocks and ETFs prices."
        },
        {
            "name": "Health",
            "description": "Check API health status."
        }
    ]
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust to RapidAPI origins in production if needed
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Default root endpoint
@app.get("/", tags=["Default"])
async def read_root():
    return {"message": "Welcome to the Real-Time Stock Price API. Use /stock/{symbol} to get prices."}

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}

# Endpoint to scrape stock price
@app.get("/stock/{symbol}", tags=["Stock Prices"], description="Fetch the real-time stock price for a given symbol, supports ETFs. ~5-second latency.")
async def get_stock_price(symbol: str):
    symbol = symbol.upper()
    yahoo_finance_url = f"https://finance.yahoo.com/quote/{symbol}/"

    # Define the schema for extracting the price
    schema = {
        "baseSelector": "div.container.yf-16vvaki",
        "fields": [
            {
                "name": "price",
                "selector": "span",
                "type": "text"
            }
        ]
    }

    # Browser configuration
    browser_config = BrowserConfig(
        headless=True,
        user_agent_mode="random",
        text_mode=True,
        light_mode=True,
    )

    # JavaScript to click the cookie accept button
    click_cookie_button_js = """
    (function() {
        const acceptButton = document.querySelector('button.accept-all');
        if (acceptButton) {
            acceptButton.click();
            console.log('Clicked cookie accept button.');
        } else {
            console.log('Cookie accept button not found using selector "button.accept-all".');
        }
    })();
    """

    # Crawler configuration
    config = CrawlerRunConfig(
        exclude_external_links=True,
        remove_overlay_elements=True,
        extraction_strategy=JsonCssExtractionStrategy(schema=schema),
        scraping_strategy=LXMLWebScrapingStrategy(),
        js_code=click_cookie_button_js,
        wait_for="css:body",
    )

    logger.info(f"Attempting to crawl: {yahoo_finance_url}")
    
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(config=config, url=yahoo_finance_url)
            logger.info(f"Raw extracted content: {result.extracted_content}")
            
            if not result.extracted_content:
                logger.error("No extracted content found.")
                raise HTTPException(status_code=404, detail="Price not found for the given symbol.")
            
            data = json.loads(result.extracted_content)
            price = data[0].get("price", None) if data else None

            if not price:
                logger.error("Price not found in extracted data.")
                raise HTTPException(status_code=404, detail="Price not found in the extracted data.")
            
            return {"symbol": symbol, "price": price}
    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to parse extracted data: {str(e)}")
    except Exception as e:
        logger.error(f"Error during crawl: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching stock price: {str(e)}")

# Run the app (for Render deployment and local testing)
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Use $PORT from Render, fallback to 8000
    uvicorn.run(app, host="0.0.0.0", port=port)