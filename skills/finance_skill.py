# skills/finance_skill.py
import yfinance as yf

def get_stock_price(app, ticker, **kwargs):
    """Fetches the current stock price for a given ticker symbol."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        price = info.get('regularMarketPrice') or info.get('currentPrice')
        name = info.get('longName', ticker.upper())
        
        if not price:
            # --- FIX: Return a structured error ---
            return {"error": f"I couldn't find a current price for the ticker symbol {ticker}."}
            
        # On success, return the normal string
        return f"The current price for {name} is ${price:.2f}."
    except Exception as e:
        app.queue_log(f"yfinance Error for ticker '{ticker}': {e}")
        # --- FIX: Return a structured error ---
        return {"error": f"I'm sorry, I had trouble finding stock information for {ticker}."}

def register():
    """Registers the stock information command."""
    return {
        'get_stock_price': {
            'handler': get_stock_price,
            'regex': r'^\s*what(?:\'s| is) the(?: current)? stock price for (.+)',
            'params': ['ticker'],
            'description': "Gets the current stock price for a given company ticker symbol."
        }
    }