# Load Test Results

## Test: Prometheus Metrics Endpoint
- **Date**: 2026-03-29
- **Tool**: Locust (Python)
- **Endpoint**: `GET http://localhost:9090/metrics`
- **Concurrent users**: 10
- **Duration**: 15 seconds

### Results

| Metric | Value |
|--------|-------|
| Total requests | 60 |
| Failures | 0 |
| Avg response time | 2053 ms |
| p95 response time | 2100 ms |
| RPS | 4.0 |

## JMeter Test Plan
Available at `tests/jmeter/dating_bot_load_test.jmx` for full webhook load testing.

## How to run full test
```bash
# Locust (headless)
locust -f tests/load/locustfile.py --headless -u 50 -r 10 -t 60s --html tests/load/report.html

# JMeter
jmeter -n -t tests/jmeter/dating_bot_load_test.jmx -l results.csv -e -o report/
```
