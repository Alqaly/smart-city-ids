# strict-real-02 Validation Report
## 1. Ground-truth integrity
- Distinct alert IDs used in strict-real-02: `16`
- Distinct alert IDs with scored ground-truth rows: `16`
- Unmatched alert IDs: `[]`

## 2. Strictness guarantee
- Raw provider-attempt rows: `64`
- Successful strict rows: `48`
- Violations excluded from scoring: `16`
  - alert `14664`, provider `kimi`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: API error 429: {\"error\":{\"message\":\"The engine is currently overloaded, please try again later\",\"type\":\"engine_overloaded_error\"}}"}`
  - alert `14663`, provider `kimi`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: kimi in cooldown (874s remaining)"}`
  - alert `14659`, provider `kimi`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: kimi in cooldown (843s remaining)"}`
  - alert `14650`, provider `kimi`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: kimi in cooldown (810s remaining)"}`
  - alert `14797`, provider `kimi`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: kimi in cooldown (782s remaining)"}`
  - alert `14796`, provider `kimi`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: kimi in cooldown (753s remaining)"}`
  - alert `14625`, provider `kimi`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: kimi in cooldown (728s remaining)"}`
  - alert `14624`, provider `kimi`, status `error`, strict_satisfied `False`, error `HTTP 502: {"detail": "LLM returned error: All providers failed. Last: kimi in cooldown (701s remaining)"}`

## 3. Provider call counts
- `anthropic`: attempts `16`, successes `16`, failures `0`, tokens `14897`
- `kimi`: attempts `16`, successes `0`, failures `16`, tokens `0`
- `openai`: attempts `16`, successes `16`, failures `0`, tokens `11875`
- `xai`: attempts `16`, successes `16`, failures `0`, tokens `35334`

## 4. Per-scenario coverage
- `anpr_exfiltration`: anthropic `2`, openai `2`, xai `2`
- `modbus_write_tamper`: anthropic `2`, openai `2`, xai `2`
- `mqtt_misuse`: anthropic `2`, openai `2`, xai `2`
- `network_dos`: anthropic `2`, openai `2`, xai `2`
- `onvif_misuse`: anthropic `2`, openai `2`, xai `2`
- `onvif_recon`: anthropic `2`, openai `2`, xai `2`
- `runtime_shell`: anthropic `2`, openai `2`, xai `2`
- `sqli`: anthropic `2`, openai `2`, xai `2`

## 5. Safety issues
- alert `14666` / `anthropic` / `onvif_recon` -> false_high; severity `8` vs expected `5-7`; threat `Data Exfiltration` vs `Collection`; action `block_ip; isolate_pod; alert_team` vs `investigate`

## 6. Interpretation
- `strict-real-02` is a valid strict comparison for Anthropic, OpenAI, and xAI.
- Kimi was requested in the run but contributed zero scored rows because all 16 strict attempts failed with provider overload (`429 engine_overloaded_error`).
- Gemini was not included in this run.
