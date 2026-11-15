Read the existing SciVerify evaluation architecture and the completed Phase 17 implementation before making any changes.

Implement **Phase 18: Live Evaluation Reliability & Retrieval Diagnostics**.

The goal is to make the real research-paper live benchmark more reliable, observable, and resumable without changing the existing verification logic or offline evaluation behavior.

### Main objectives

1. **Structured live failure handling**

   * Review the existing `LiveFailureCategory` system.
   * Ensure retrieval and LLM failures are consistently classified into meaningful categories such as:

     * `DOI_NOT_FOUND`
     * `FULL_TEXT_UNAVAILABLE`
     * `ANTI_BOT_BLOCKED`
     * `PAYWALLED`
     * `RETRIEVAL_ERROR`
     * `LLM_TIMEOUT`
     * `LLM_QUOTA_EXCEEDED`
     * other existing categories already defined by the project.
   * Avoid misclassifying retrieval failures as verification/LLM failures.

2. **Per-case live result tracking**

   * Ensure every live benchmark case produces a structured result containing its status, failure category/reason when applicable, retrieval information, and verification result when successful.
   * Preserve successful, failed, and skipped cases separately.

3. **Retrieval diagnostics**

   * Capture useful retrieval information such as number of retrieval attempts, candidate URLs attempted, failure reasons, and elapsed time.
   * Clearly distinguish invalid PDFs, HTTP failures, paywalls, anti-bot/interstitial pages, and unavailable full text.
   * Do not bypass publisher access controls.

4. **Bounded retries**

   * Ensure transient retrieval failures use bounded retries with configurable retry limits/backoff.
   * Permanent failures such as DOI-not-found or unavailable full text should not waste repeated retries.
   * Preserve the existing LLM quota-abort behavior from Phase 17.

5. **Live reporting**

   * Improve live JSON and Markdown reports so they contain:

     * overall live benchmark summary
     * per-case results
     * success/failure/skip counts
     * failure-category counts
     * retrieval diagnostics
     * verification metrics for successfully evaluated cases
     * timing information
     * resume/checkpoint information where applicable.
   * Reports must remain useful even when the live run terminates early because of quota exhaustion or another external failure.

6. **Checkpoint compatibility**

   * Preserve the existing Phase 17 checkpoint format and resume behavior.
   * Do not break existing `--resume` or `--resume-live`.
   * Existing completed cases must remain completed.
   * Quota failures must remain retryable.
   * Permanent retrieval failures must remain non-retryable.

### Constraints

* Do NOT modify the core verification/prosecutor/defender/adjudicator logic unless absolutely required.
* Do NOT break offline evaluation.
* Do NOT modify the baseline silently.
* Do NOT add LLM calls to offline tests/evaluation.
* Do NOT expose API keys or modify `.env`.
* Preserve the existing frontend.
* Keep the implementation backward compatible with the current 339-test baseline.
* Prefer small, focused changes over rewriting existing evaluation infrastructure.

### Testing

Add or update deterministic tests for:

* each important failure classification
* retrieval retry behavior
* permanent vs transient failures
* per-case live result tracking
* report generation
* early quota termination
* checkpoint/resume compatibility
* legacy checkpoint compatibility if applicable.

Run the complete test suite after implementation and confirm there are no regressions.

### Final output

After implementation, report:

* files changed
* what was implemented
* tests added/updated
* complete test result
* any live-evaluation validation performed
* remaining external limitations/blockers.

Do not start Phase 19. Stop after Phase 18 is implemented and validated.
