# strict-real-01 Validation Report
## 1. Ground-truth integrity
- Distinct alert IDs used in strict-real-01: `14`
- Distinct alert IDs with scored ground-truth rows: `14`
- Unmatched alert IDs: `[]`

## 2. Strictness guarantee
- Raw provider-attempt rows: `42`
- Successful strict rows: `41`
- Violations excluded from scoring: `1`
  - alert `14295`, provider `xai`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: "}`

## 3. Provider call counts
- `kimi`: attempts `14`, successes `14`, failures `0`, scored alerts `14`
- `openai`: attempts `14`, successes `14`, failures `0`, scored alerts `14`
- `xai`: attempts `14`, successes `13`, failures `1`, scored alerts `13`

## 4. Latency sanity check
- `kimi`: summary avg `3.7296s`, summary p95 `5.32s` (recomputed from raw rows and matched exactly).
- `openai`: summary avg `2.2774s`, summary p95 `3.054s` (recomputed from raw rows and matched exactly).
- `xai`: summary avg `25.4889s`, summary p95 `28.854s` (recomputed from raw rows and matched exactly).

## 5. Token and cost recomputation
- `kimi`: total tokens `11667`, estimated cost total `$0.070002`, cost/alert `$0.005000`, cost/1000 `$5.00`.
- `openai`: total tokens `10713`, estimated cost total `$0.107130`, cost/alert `$0.007652`, cost/1000 `$7.65`.
- `xai`: total tokens `28943`, estimated cost total `$0.228588`, cost/alert `$0.017584`, cost/1000 `$17.58`.

## 6. Per-scenario coverage in strict-real-01
- `anpr_exfiltration`: kimi `2`, openai `2`, xai `1`
- `lateral_movement_or_platform_access`: kimi `2`, openai `2`, xai `2`
- `modbus_write_tamper`: kimi `2`, openai `2`, xai `2`
- `mqtt_misuse`: kimi `2`, openai `2`, xai `2`
- `onvif_misuse`: kimi `2`, openai `2`, xai `2`
- `onvif_recon`: kimi `2`, openai `2`, xai `2`
- `runtime_shell`: kimi `2`, openai `2`, xai `2`

## 7. Safety issue rows
- alert `14165` / `xai` / `lateral_movement_or_platform_access` -> under_escalation; severity `3` vs expected `4-7`; threat `Policy Violation` vs expected `Lateral Movement`; action `alert_team` vs expected `investigate`
- alert `14164` / `xai` / `lateral_movement_or_platform_access` -> under_escalation; severity `2` vs expected `4-7`; threat `Policy Violation` vs expected `Lateral Movement`; action `alert_team` vs expected `investigate`

## 8. xAI failure mode
- xAI failed on alert `14295` with error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: "}`.

## 9. Small strict comparison check
- Smoke run directory: `artifacts/llm-eval/strict-smoke-01`
- Alerts exported: `24`; scenario families scored: `8`; successful strict runs: `24`; failed strict runs: `0`
  - `kimi`: quality `70.0%`, severity `100.0%`, threat `37.5%`, avg latency `3.7908s`
  - `openai`: quality `60.0%`, severity `87.5%`, threat `25.0%`, avg latency `2.5636s`
  - `xai`: quality `70.0%`, severity `100.0%`, threat `37.5%`, avg latency `21.0587s`

## 10. Family-cap check
- The strict-real-01 artifact preserves only the kept rows, not the pre-cap candidate pool. Exact original pre-cap counts are therefore not reconstructable from the artifact alone.
- Current live reconstruction from `/api/alerts?limit=400` matched the following family counts before capping: {"anpr_exfiltration": 4, "modbus_write_tamper": 7, "mqtt_misuse": 29, "network_dos": 20, "onvif_misuse": 5, "onvif_recon": 11, "runtime_shell": 19, "sqli": 14}
- With `--max-per-family 2`, the current live selector would keep: {"anpr_exfiltration": 2, "modbus_write_tamper": 2, "mqtt_misuse": 2, "network_dos": 2, "onvif_misuse": 2, "onvif_recon": 2, "runtime_shell": 2, "sqli": 2}

## 11. Five-provider readiness
- `kimi`: status `success`, strict_satisfied `True`, error `None`
- `openai`: status `success`, strict_satisfied `True`, error `None`
- `xai`: status `success`, strict_satisfied `True`, error `None`
- `gemini`: status `error`, strict_satisfied `False`, error `All providers failed. Last: gemini in cooldown (236s remaining)`
- `anthropic`: status `error`, strict_satisfied `False`, error `All providers failed. Last: anthropic auth_failed (disabled)`

## 12. Gap to a 500 x 5-provider study
- Current strict-real-01 provider attempts: `42`. Additional provider attempts needed to reach 500: `458`.
- Current distinct alerts used: `14`. Additional distinct alerts needed to reach 100 alerts: `86`.
- Current blockers: `gemini` in cooldown/quota state; `anthropic` auth failed.
