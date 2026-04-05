# Metrics Audit & Defensibility

Audit of Prometheus metrics and Grafana dashboards — ensuring they are realistic, defensible, and directly tied to emulated IIoT system behavior.

---

### Task 4: Making Metrics Realistic and Defensible

The primary goal of monitoring in this emulation is **not** just visualization; it is **measurement**. Every graph must answer a question about the system's state, performance, or security posture. Metrics that are easy to expose but don't represent a meaningful, real-world event should be removed.

#### Audit of Existing Metrics

The current system exposes several default metrics from the Python services and Kubernetes.

1.  **HTTP Requests (`http_requests_total`, `http_requests_duration_seconds`)**:
    *   **What produces it?**: The FastAPI middleware in the `ids-api` and the Flask middleware in the `smart-city-services`.
    *   **Is it realistic?**: Yes. These are standard, essential metrics for any web service. They measure the load and latency of the API endpoints.
    *   **SOC/IIoT Platform Value**: High. A sudden spike in request latency or 5xx errors on the `ids-api` could indicate that the system is under a DoS attack or that the LLM engine is failing.

2.  **LLM Analysis Metrics (`llm_analysis_requests_total`, `llm_analysis_duration_seconds`)**:
    *   **What produces it?**: Custom counters and histograms in the `ids-api` around the call to the xAI/OpenAI LLM.
    *   **Is it realistic?**: Yes. This is a critical custom metric. It measures the performance and cost driver of the system.
    *   **SOC/IIoT Platform Value**: High. Tracking the duration is vital for SLOs (Service Level Objectives). If the average analysis time exceeds a threshold, the system's ability to respond in real-time is compromised. Tracking the total count is essential for budget monitoring.

3.  **Kubernetes Metrics (`kube_pod_status_phase`, `container_cpu_usage_seconds_total`, etc.)**:
    *   **What produces it?**: The Kubernetes `kube-state-metrics` service that Prometheus scrapes.
    *   **Is it realistic?**: Yes. These are fundamental to understanding the health of the underlying infrastructure.
    *   **SOC/IIoT Platform Value**: High. A spike in container restarts for a specific deployment (e.g., `emulated-compromised-device`) is a direct, measurable indicator of anomalous behavior that correlates with the liveness probe I configured. CPU usage can indicate resource exhaustion attacks.

4.  **MQTT Metrics (Current Gap)**:
    *   **What produces it?**: Currently, nothing. The `iot-device` does not expose Prometheus metrics.
    *   **Is it realistic?**: This is a **major gap**. A real IIoT platform would absolutely have metrics on MQTT message volume, client connections, and errors from the broker.
    *   **Recommendation**: For full academic rigor, the MQTT broker (e.g., Mosquitto) should be configured to expose metrics, and Prometheus should scrape them. This would allow the dashboards to show a direct correlation between emulated device traffic and broker load.

#### Refactoring Grafana Dashboards

Grafana dashboards must be refactored to be investigative tools, not just "single pane of glass" displays. They must answer three key questions:

1.  **What is happening? (The "What")**
    *   *Example Panel*: "LLM Analysis Rate" (requests per minute).
    *   *Metric*: `rate(llm_analysis_requests_total[5m])`
    *   *Purpose*: Shows the current load on the most expensive component of the IDS.

2.  **Why is it happening? (The "Why")**
    *   *Example Panel*: "Falco Alerts by Rule" (pie chart or table).
    *   *Metric*: `sum by (rule) (rate(falco_alerts_total[5m]))` (Assuming a `falco_alerts_total` metric is exposed by the forwarder).
    *   *Purpose*: Correlates the load on the LLM with the specific security events being detected. If the LLM analysis rate is high, this panel shows *why*—e.g., because of a spike in "Unexpected Shell in Container" alerts.

3.  **Is it expected or malicious? (The "Verdict")**
    *   *Example Panel*: "Automated Actions Taken" (table or stat panel).
    *   *Metric*: `sum by (action) (rate(ids_automated_actions_total[5m]))`
    *   *Purpose*: Shows the final output of the system. This panel answers the question of whether the observed events were severe enough to trigger a defensive action, such as `isolate_pod`.

By structuring dashboards this way, they become a narrative tool that tells the story of an event, from detection to analysis to response. This is infinitely more defensible than a collection of unrelated graphs.
