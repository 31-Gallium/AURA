# skills/finance_skill.py
import yfinance as yf
import requests_cache

def get_stock_price(app, ticker, **kwargs):
    """Fetches the current stock price for a given ticker symbol."""
    session = requests_cache.CachedSession('yfinance.cache')
    session.headers['User-agent'] = 'AURA/1.0'
    
    try:
        stock = yf.Ticker(ticker, session=session)
        info = stock.info
        
        # Use 'regularMarketPrice' or 'currentPrice' as fallbacks
        price = info.get('regularMarketPrice') or info.get('currentPrice')
        name = info.get('longName', ticker.upper())
        
        if not price:
            return f"I couldn't find a current price for the ticker symbol {ticker}."
            
        return f"The current price for {name} is ${price:.2f}."
    except Exception as e:
        app.queue_log(f"yfinance Error for ticker '{ticker}': {e}")
        return f"I'm sorry, I had trouble finding stock information for {ticker}."

def register():
    """Registers the stock information command."""
    return {
        'get_stock_price': {
            'handler': get_stock_price,
            'regex': r'\bwhat(?:\'s| is) the(?: current)? stock price for (.+)\b',
            'params': ['ticker'],
            'description': "Gets the current stock price for a given company ticker symbol."
        }
    }