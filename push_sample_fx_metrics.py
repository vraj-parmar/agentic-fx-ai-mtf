from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import time
import random

# --- Configuration ---
PUSHGATEWAY_URL = 'http://localhost:9091'  # Address of our port-forwarded Pushgateway
JOB_NAME = 'fx_ohlcv_ingestor'  # A name for the job pushing these metrics
CURRENCY_PAIR = 'GBPUSD'
TIMEFRAME = '1m'


def push_sample_metrics():
    registry = CollectorRegistry()

    # Define our Gauge metrics. Gauges can go up and down.
    # For OHLCV, each component is a separate gauge.
    g_open = Gauge('fx_ohlcv_open', 'Open price of the candle', ['currency_pair', 'timeframe'], registry=registry)
    g_high = Gauge('fx_ohlcv_high', 'High price of the candle', ['currency_pair', 'timeframe'], registry=registry)
    g_low = Gauge('fx_ohlcv_low', 'Low price of the candle', ['currency_pair', 'timeframe'], registry=registry)
    g_close = Gauge('fx_ohlcv_close', 'Close price of the candle', ['currency_pair', 'timeframe'], registry=registry)
    g_volume = Gauge('fx_ohlcv_volume', 'Volume of the candle', ['currency_pair', 'timeframe'], registry=registry)

    # --- Simulate some data for a single 1-minute candle ---
    # In a real scenario, this data would come from your API
    open_price = round(1.2500 + random.uniform(-0.0005, 0.0005), 4)
    close_price = round(open_price + random.uniform(-0.0010, 0.0010), 4)
    high_price = round(max(open_price, close_price) + random.uniform(0, 0.0005), 4)
    low_price = round(min(open_price, close_price) - random.uniform(0, 0.0005), 4)
    volume = random.randint(100, 1000)
    # --- End of simulated data ---

    print(f"Pushing metrics for {CURRENCY_PAIR} ({TIMEFRAME}):")
    print(f"  Open: {open_price}, High: {high_price}, Low: {low_price}, Close: {close_price}, Volume: {volume}")

    # Set the values for the current candle
    g_open.labels(currency_pair=CURRENCY_PAIR, timeframe=TIMEFRAME).set(open_price)
    g_high.labels(currency_pair=CURRENCY_PAIR, timeframe=TIMEFRAME).set(high_price)
    g_low.labels(currency_pair=CURRENCY_PAIR, timeframe=TIMEFRAME).set(low_price)
    g_close.labels(currency_pair=CURRENCY_PAIR, timeframe=TIMEFRAME).set(close_price)
    g_volume.labels(currency_pair=CURRENCY_PAIR, timeframe=TIMEFRAME).set(volume)

    try:
        # Push metrics to Pushgateway
        # The 'grouping_key' helps manage metrics in Pushgateway.
        # If you push again with the same job and grouping_key, it replaces the previous metrics for that group.
        push_to_gateway(PUSHGATEWAY_URL, job=JOB_NAME, registry=registry,
                        grouping_key={'instance': f'{CURRENCY_PAIR}_{TIMEFRAME}'})
        print(f"Successfully pushed metrics to Pushgateway at {PUSHGATEWAY_URL}")
    except Exception as e:
        print(f"Error pushing to Pushgateway: {e}")


if __name__ == '__main__':
    push_sample_metrics()
