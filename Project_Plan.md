# Project Plan: Agentic AI for FX Multi-Timeframe Analysis

## Phase 1: Multi-Timeframe Data Infrastructure with Prometheus

**1.1. Prometheus Setup & Configuration**
    1.1.1. Research and select Prometheus deployment option (Local Docker, direct binary, Prometheus Operator on Kubernetes if applicable).
    1.1.2. Install and configure the chosen Prometheus instance.
    1.1.3. Configure Prometheus targets (e.g., a Pushgateway or a custom exporter for historical data).
    1.1.4. Secure Prometheus instance (often via reverse proxy for authentication/authorization).
    1.1.5. Verify connection to Prometheus instance using Prometheus UI (Graph) and API.

**1.2. Prometheus Metric Design for OHLCV Data**
    1.2.1. Define Prometheus metric naming conventions.
    1.2.2. Design how 1-minute OHLCV data will be represented as Prometheus metrics.
        *   **Note:** Prometheus typically stores individual metrics. OHLCV might be stored as separate metrics (e.g., `fx_price_open`, `fx_price_high`, `fx_price_low`, `fx_price_close`, `fx_volume`) with labels like `currency_pair` and potentially `original_timeframe="1m"`.
        *   Alternatively, explore if a single metric with multiple values per timestamp is feasible or if an exporter/Pushgateway can structure data appropriately. This is less standard for Prometheus.
    1.2.3. Document the metric and label design choices.
    1.2.4. Consider long-term storage solutions if extensive history is needed (e.g., Thanos, Mimir, or remote write configurations), as Prometheus's local TSDB is often tuned for operational data retention.

**1.3. Automated Data Ingestion Pipeline (1-minute data)**
    1.3.1. Identify and select free API(s) for 1-minute historical FX data.
    1.3.2. Develop Python script to fetch data from the selected API.
    1.3.3. Implement data parsing and cleaning for the fetched data.
    1.3.4. Integrate a mechanism to expose/push data to Prometheus:
        *   Option A: Use `prometheus_client` (Python) to create metrics and expose them via an HTTP endpoint for Prometheus to scrape.
        *   Option B: Push data to a Prometheus Pushgateway, especially for batch jobs or short-lived scripts.
    1.3.5. Implement error handling, logging, and retry mechanisms for the ingestion script.
    1.3.6. Schedule the script for periodic data updates or manage backfill processes.

**1.4. Data Aggregation & Querying with PromQL**
    1.4.1. Learn and practice PromQL syntax for filtering, aggregation, and time-series functions.
    1.4.2. Develop PromQL queries to retrieve data for different timeframes.
        *   **Note:** Dynamically creating full OHLCV bars for higher timeframes (e.g., 1-hour OHLCV from 1-minute data) purely with PromQL on-the-fly is more complex than with Flux.
        *   You will likely query the raw 1-minute metrics (e.g., `fx_price_open`, `fx_price_high`, etc.) over the desired window.
        *   Aggregation functions like `max_over_time` (for High), `min_over_time` (for Low), `sum_over_time` (for Volume) will be used.
        *   For Open and Close of a higher timeframe bar, you'd query the relevant 1-minute metric (e.g., `fx_price_close`) over the window and then programmatically determine the first/last value in your Python application after fetching the data, or use subqueries/offsets carefully.
    1.4.3. Test PromQL queries for accuracy and performance.
    1.4.4. Consider using Prometheus recording rules to pre-aggregate certain views if query-time performance for complex aggregations becomes an issue, though this creates new metrics rather than being fully dynamic.
    1.4.5. The primary "resampling" logic to construct higher-timeframe OHLCV bars will likely reside in the Python data processing layer after fetching data via PromQL.

## Phase 2: Data Preprocessing & Feature Engineering

**2.1. Technical Indicator Calculation**
    2.1.1. Select a set of relevant technical indicators (e.g., RSI, MACD, Bollinger Bands, Moving Averages).
    2.1.2. Implement functions (using `pandas-ta` or `ta-lib` via Python wrappers) to calculate these indicators on data retrieved (and potentially reconstructed into OHLCV DataFrames) for various timeframes.
    2.1.3. Integrate indicator calculation into the data loading pipeline for model training.

**2.2. Statistical Feature Engineering**
    2.2.1. Identify useful statistical features (e.g., mean, std dev, skewness, kurtosis, volatility measures like ATR) across different timeframes.
    2.2.2. Implement functions to calculate these statistical features on data retrieved and processed from Prometheus.
    2.2.3. Integrate statistical feature calculation into the data loading pipeline.

**2.3. Cross-Timeframe Feature Engineering**
    2.3.1. Design features that capture relationships between timeframes (e.g., current price vs. higher timeframe MA, lower timeframe volatility relative to higher timeframe trend).
    2.3.2. Implement functions to calculate these cross-timeframe features.
    2.3.3. Ensure proper alignment of data from different timeframes when calculating these features (this will be crucial in the Python layer).

**2.4. Data Normalization & Scaling**
    2.4.1. Research and select appropriate scaling techniques (e.g., StandardScaler, MinMaxScaler).
    2.4.2. Implement data normalization/scaling for all features.
    2.4.3. Ensure scalers are fit only on training data and applied to validation/test data to prevent data leakage.

## Phase 3: Agentic AI Model Design & Implementation

**(No changes in this section based on the database choice, assuming data is correctly prepared in Python before feeding to the model)**

**3.1. Foundational Model Research & Selection**
    3.1.1. Research pros and cons of LSTM, GRU, and Transformer architectures for time-series forecasting.
    3.1.2. Select an initial base model architecture (e.g., LSTM) for the first iteration.
    3.1.3. Set up the development environment with TensorFlow or PyTorch.

**3.2. Multi-Input Model Architecture Design**
    3.2.1. Design how features from different timeframes will be fed into the model (e.g., concatenation, separate input branches, attention mechanisms).
    3.2.2. Define the input shape(s) and output shape (e.g., predicting next N price points or price direction).
    3.2.3. Implement the multi-input model architecture using the chosen deep learning framework.

**3.3. Model Training Pipeline**
    3.3.1. Implement data loading and batching for training, preparing sequences of multi-timeframe features.
    3.3.2. Implement the training loop (forward pass, loss calculation, backpropagation, optimizer step).
    3.3.3. Select an appropriate loss function (e.g., MSE for regression, Cross-Entropy for classification if predicting direction).
    3.3.4. Implement walk-forward validation split for training and validation sets.

**3.4. Model Checkpointing & Experiment Tracking**
    3.4.1. Implement model checkpointing to save the best performing models during training.
    3.4.2. Set up a basic experiment tracking system (e.g., logging metrics to a CSV, or using a free tier of a tool like MLflow or Weights & Biases if desired, though simple logging is fine to start).

**3.5. Hyperparameter Tuning Strategy**
    3.5.1. Identify key hyperparameters for tuning (e.g., learning rate, batch size, number of layers/units, sequence length).
    3.5.2. Select a hyperparameter tuning strategy (e.g., manual tuning, grid search, or using a library like Optuna).
    3.5.3. Implement the chosen tuning strategy.

## Phase 4: Rigorous Evaluation & Backtesting

**(Minor change for Grafana data source)**

**4.1. Walk-Forward Backtesting Framework**
    4.1.1. Design and implement a robust walk-forward backtesting framework that simulates real-world deployment.
        4.1.1.1. Ensure no future data leakage into training periods.
        4.1.1.2. Define rolling window or expanding window strategy for training.
    4.1.2. Integrate the trained model into the backtesting framework for generating predictions on unseen data.

**4.2. Evaluation Metrics Implementation**
    4.2.1. Implement calculation for key performance metrics:
        4.2.1.1. Regression metrics: MAE, RMSE, MAPE.
        4.2.1.2. Directional accuracy.
        4.2.1.3. (Optional) Trend alignment metrics.
    4.2.2. Develop a system to aggregate and report these metrics from backtesting runs.

**4.3. Results Visualization**
    4.3.1. Implement visualizations for backtesting results (e.g., actual vs. predicted prices, equity curve if simulating trades, metric plots).
    4.3.2. Utilize Matplotlib, Seaborn, or Plotly for creating these visualizations.
    4.3.3. (Optional) Explore Grafana (community edition) for dashboarding Prometheus data and potentially model outputs.

## Phase 5: Initial Use Case & Agentic Refinement

**(No changes in this section based on the database choice)**

**5.1. Target Market & Data Preparation for Use Case**
    5.1.1. Select a specific currency pair for the initial detailed use case (e.g., GBPUSD as per proposal).
    5.1.2. Ensure sufficient historical data for this pair is ingested and processed.

**5.2. End-to-End Training & Evaluation of Initial Model**
    5.2.1. Train the multi-timeframe agentic AI model on the selected currency pair.
    5.2.2. Perform a full backtest and evaluate using the defined metrics.
    5.2.3. Analyze the results, identify weaknesses and areas for improvement.

**5.3. Agentic Component Refinement (Initial Pass)**
    5.3.1. Review how the model "perceives" multiple timeframes and if the current architecture effectively synthesizes this information.
    5.3.2. Consider simple "memory" implementations (e.g., using LSTM/GRU states).
    5.3.3. Evaluate if the model's "planning" (i.e., feature selection and weighting implicitly learned) leads to reasonable forecasts.
    5.3.4. Document observations for future enhancements towards more explicit agentic behaviors.

## Phase 6: Project Management, Documentation & Iteration

**(No changes in this section based on the database choice)**

**6.1. Version Control & Collaboration**
    6.1.1. Initialize Git repository on GitHub (or similar).
    6.1.2. Define branching strategy (e.g., main, develop, feature branches).
    6.1.3. Consistently use task identifiers (e.g., `[1.1.2]`) in commit messages.

**6.2. Documentation**
    6.2.1. Maintain and update this project plan (`.md` file).
    6.2.2. Add comprehensive README.md with project overview, setup instructions, and usage.
    6.2.3. Document code with comments and docstrings.
    6.2.4. Document architectural decisions and data schemas.

**6.3. Iteration and Future Work Planning**
    6.3.1. Regularly review progress against the plan.
    6.3.2. Based on initial results, prioritize future work items (e.g., exploring different model architectures, reinforcement learning, sentiment integration).
    6.3.3. Continuously refine the model and system based on learnings.