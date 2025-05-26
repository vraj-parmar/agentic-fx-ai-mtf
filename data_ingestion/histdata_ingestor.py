# File: agentic-fx-ai-mtf/data_ingestion/histdata_ingestor.py

import requests
import zipfile
import csv
import io
from datetime import datetime
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import time  # Not strictly used in the current flow but good to keep for potential future use
import logging
from bs4 import BeautifulSoup  # For parsing HTML
from urllib.parse import urljoin  # To construct absolute URLs

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
PUSHGATEWAY_URL = 'http://localhost:9091'
JOB_NAME = 'histdata_fx_ingestor'
# How many candles to include in each push to Pushgateway
# Adjust this based on performance and Pushgateway stability.
# Now 4 metrics/candle (O, H, L, C)
# e.g., 1000 candles * 4 metrics/candle = 4000 series per push.
PUSH_SUB_BATCH_SIZE = 1000

# --- Supported Datetime Formats for Histdata CSV ---
HISTDATA_DATETIME_FORMATS = [
    '%Y%m%d %H%M%S',
    '%Y.%m.%d %H:%M',
    '%Y%m%d%H%M%S',
]

# --- Histdata Specifics ---
HISTDATA_BASE_URL = "https://www.histdata.com/download-free-forex-historical-data/"
HISTDATA_POST_ACTION_URL_SEGMENT = "?/ascii/1-minute-bar-quotes/"


def fetch_and_extract_histdata_csv(currency_pair, year, month):
    # Fetches data from Histdata.com for a specific pair, year, and month.
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': HISTDATA_BASE_URL
    })

    get_url = f"{HISTDATA_BASE_URL}{HISTDATA_POST_ACTION_URL_SEGMENT}{currency_pair.lower()}/{year}/{month}"
    logging.info(f"Fetching form page from: {get_url}")

    try:
        response_get = session.get(get_url, timeout=30)
        response_get.raise_for_status()
        soup = BeautifulSoup(response_get.content, 'html.parser')

        form = soup.find('form', {'id': 'file_down'})
        if not form:
            logging.error("Could not find the download form on the page.")
            return None

        form_action = form.get('action')
        post_url = urljoin(get_url, form_action) if form_action else get_url
        logging.info(f"Form action URL determined as: {post_url}")

        form_inputs = {
            input_tag['name']: input_tag['value']
            for input_tag in form.find_all('input', {'name': True, 'value': True})
        }

        required_fields = ['tk', 'date', 'datemonth', 'platform', 'timeframe', 'fxpair']
        if not all(field in form_inputs for field in required_fields):
            logging.error(f"One or more required form input fields were not found. Found: {list(form_inputs.keys())}")
            return None

        payload = {field: form_inputs[field] for field in required_fields}
        logging.info(f"Extracted form data for POST: {payload}")

        logging.info(f"Submitting POST request to download ZIP from: {post_url}")
        session.headers.update({'Referer': get_url})
        response_post = session.post(post_url, data=payload, stream=True, timeout=60)
        response_post.raise_for_status()

        content_type = response_post.headers.get('Content-Type', '').lower()
        if not any(zip_type in content_type for zip_type in
                   ['application/zip', 'application/octet-stream', 'application/x-zip-compressed']):
            logging.error(f"Expected a ZIP file, but got Content-Type: {content_type}")
            if 'text' in content_type or 'html' in content_type:
                logging.error(f"Response text (first 500 chars): {response_post.text[:500]}")
            return None

        with io.BytesIO(response_post.content) as zip_buffer:
            with zipfile.ZipFile(zip_buffer) as zf:
                csv_file_name = next((member for member in zf.namelist() if member.lower().endswith('.csv')), None)
                if not csv_file_name:
                    logging.error("No CSV file found in the downloaded ZIP.")
                    return None
                logging.info(f"Extracting {csv_file_name} from downloaded ZIP...")
                csv_content_bytes = zf.read(csv_file_name)
                return csv_content_bytes.decode('utf-8')

    except requests.exceptions.RequestException as e:
        logging.error(f"Error during Histdata fetch/download: {e}")
    except (AttributeError, TypeError, KeyError) as e:
        logging.error(f"Error parsing HTML or form data: {e}")
    except zipfile.BadZipFile:
        logging.error("Downloaded file is not a valid ZIP archive.")
    except Exception as e:
        logging.error(f"An unexpected error occurred during Histdata processing: {e}")
    return None


def parse_datetime_from_row(row_data):
    datetime_str_candidate = row_data[0].strip()
    for fmt in HISTDATA_DATETIME_FORMATS:
        try:
            return datetime.strptime(datetime_str_candidate, fmt)
        except ValueError:
            continue
    if len(row_data) > 1:
        datetime_str_candidate_combined = f"{row_data[0].strip()} {row_data[1].strip()}"
        for fmt in HISTDATA_DATETIME_FORMATS:
            try:
                return datetime.strptime(datetime_str_candidate_combined, fmt)
            except ValueError:
                continue
    return None


def _push_metrics_sub_batch(registry, currency_pair, year, month, sub_batch_candle_count,
                            total_candles_processed_so_far, total_rows_in_file):
    """Helper function to push a sub-batch of metrics."""
    if sub_batch_candle_count == 0:
        return

    grouping_key_instance = f"{currency_pair}_{year}_{month:02d}"
    logging.info(
        f"Pushing sub-batch of {sub_batch_candle_count} candles "
        f"(total processed: {total_candles_processed_so_far}/{total_rows_in_file}) "
        f"to Pushgateway for group '{grouping_key_instance}'..."
    )
    try:
        push_to_gateway(
            PUSHGATEWAY_URL,
            job=JOB_NAME,
            registry=registry,
            grouping_key={'instance': grouping_key_instance},
            timeout=30  # Explicit timeout for the push operation
        )
        logging.info("Successfully pushed sub-batch.")
    except Exception as e:
        logging.error(f"Error pushing sub-batch to Pushgateway: {e}")


def parse_histdata_csv_and_push(csv_content_string, currency_pair, year, month):
    if not csv_content_string:
        logging.warning("No CSV content to parse.")
        return

    csv_file_like_object = io.StringIO(csv_content_string)
    all_rows = list(csv.reader(csv_file_like_object, delimiter=';'))
    total_rows_in_file = len(all_rows)

    logging.info(
        f"Parsing CSV for {currency_pair} ({total_rows_in_file} rows) and collecting metrics in sub-batches...")

    timeframe_label = "1m"
    candles_processed_total = 0
    candles_in_current_sub_batch = 0

    # Initialize registry and gauges for the first sub-batch
    registry = CollectorRegistry()
    g_open = Gauge('fx_ohlc_open', 'Open price', ['currency_pair', 'timeframe', 'timestamp'],
                   registry=registry)  # Changed metric name slightly
    g_high = Gauge('fx_ohlc_high', 'High price', ['currency_pair', 'timeframe', 'timestamp'],
                   registry=registry)  # Changed metric name slightly
    g_low = Gauge('fx_ohlc_low', 'Low price', ['currency_pair', 'timeframe', 'timestamp'],
                  registry=registry)  # Changed metric name slightly
    g_close = Gauge('fx_ohlc_close', 'Close price', ['currency_pair', 'timeframe', 'timestamp'],
                    registry=registry)  # Changed metric name slightly
    # Volume gauge (g_volume) is removed

    for i, row in enumerate(all_rows):
        try:
            dt_obj = parse_datetime_from_row(row)
            if not dt_obj:
                logging.warning(f"Skipping row {i + 1} due to unparsed datetime: {row}")
                continue

            ohlcv_start_index = 1
            if len(row[0].split()) == 1 and '.' not in row[0] and len(row) > 1 and ':' in row[1]:
                ohlcv_start_index = 2
            elif not (len(row[0].split()) > 1 or '.' in row[0]):
                if len(row[0].split()) == 1 and not ('.' in row[0] or ':' in row[0]):
                    ohlcv_start_index = 2
                else:
                    ohlcv_start_index = 1

            # We still expect 5 columns for O,H,L,C,V in the CSV, even if V is 0 and unused.
            # If your CSV format truly drops the volume column, this check needs to be +4
            if len(row) < ohlcv_start_index + 5:
                logging.warning(
                    f"Skipping malformed row {i + 1} (expected at least {ohlcv_start_index + 5} columns, got {len(row)}): {row}")
                continue

            open_price = float(row[ohlcv_start_index])
            high_price = float(row[ohlcv_start_index + 1])
            low_price = float(row[ohlcv_start_index + 2])
            close_price = float(row[ohlcv_start_index + 3])
            # volume = float(row[ohlcv_start_index + 4]) # Parsed but not used

            candle_timestamp_label = dt_obj.strftime('%Y%m%d%H%M%S')

            labels = [currency_pair, timeframe_label, candle_timestamp_label]
            g_open.labels(*labels).set(open_price)
            g_high.labels(*labels).set(high_price)
            g_low.labels(*labels).set(low_price)
            g_close.labels(*labels).set(close_price)
            # g_volume.labels(*labels).set(volume) # This line is removed

            candles_in_current_sub_batch += 1
            candles_processed_total += 1

            if candles_in_current_sub_batch >= PUSH_SUB_BATCH_SIZE or candles_processed_total == total_rows_in_file:
                _push_metrics_sub_batch(registry, currency_pair, year, month, candles_in_current_sub_batch,
                                        candles_processed_total, total_rows_in_file)
                candles_in_current_sub_batch = 0
                if candles_processed_total < total_rows_in_file:
                    registry = CollectorRegistry()
                    g_open = Gauge('fx_ohlc_open', 'Open price', ['currency_pair', 'timeframe', 'timestamp'],
                                   registry=registry)
                    g_high = Gauge('fx_ohlc_high', 'High price', ['currency_pair', 'timeframe', 'timestamp'],
                                   registry=registry)
                    g_low = Gauge('fx_ohlc_low', 'Low price', ['currency_pair', 'timeframe', 'timestamp'],
                                  registry=registry)
                    g_close = Gauge('fx_ohlc_close', 'Close price', ['currency_pair', 'timeframe', 'timestamp'],
                                    registry=registry)
                    # Volume gauge re-initialization is removed

        except ValueError as ve:
            logging.warning(f"Skipping row {i + 1} due to data conversion error: {row} - {ve}")
        except IndexError as ie:
            logging.warning(f"Skipping row {i + 1} due to missing columns (IndexError): {row} - {ie}")
        except Exception as e:
            logging.error(f"Error processing row {i + 1}: {row} - {e}")

    logging.info(f"Finished all processing. Total candles processed: {candles_processed_total}.")


if __name__ == '__main__':
    target_currency_pair = "EURUSD"
    target_year = 2023
    target_month = 1

    logging.info(f"Attempting to download Histdata for {target_currency_pair} {target_year}-{target_month:02d}")
    csv_data_online = fetch_and_extract_histdata_csv(target_currency_pair, target_year, target_month)

    if csv_data_online:
        logging.info(f"Successfully downloaded and extracted CSV data for {target_currency_pair}.")
        parse_histdata_csv_and_push(csv_data_online, target_currency_pair, target_year, target_month)
    else:
        logging.error(f"Failed to download or extract data for {target_currency_pair}. Check logs.")