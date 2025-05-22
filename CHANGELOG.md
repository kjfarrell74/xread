# XReader Changelog

All notable changes to XReader will be documented in this file.

## [Unreleased]

### Added
- Implemented `BaseAIModel` and `PerplexityModel` classes in `xread/ai_models.py` for modular AI model integration.
- Centralized data enhancement logic in `xread/data_enhancer.py`, used by `xread/post_enhancer.py` and `xread/json_upgrader.py`.
- Updated `xread/pipeline.py` to use the `PerplexityModel` class for report generation.
- Removed hardcoded API keys from `test_perplexity_final.py` and `test_perplexity_format.py`, enforcing environment variable usage.
- Updated documentation in `README.md`, `CONFIGURATION.md`, and `USAGE.md` to reflect multi-AI model support and centralized data enhancement.
- Added Gemini-specific prompt `GEMINI_REPORT_PROMPT` in `xread/constants.py` with an instruction to include a "Factual Context" section for structured factual output. Updated `GeminiModel` in `xread/ai_models.py` to use this prompt and enhanced `extract_factual_context` in `xread/data_enhancer.py` to parse this section. Rationale: To ensure Gemini's output is as structured and atomic as Perplexity's for factual analysis.

## [0.1.0] - 2023-10-01

### Initial Release
- Basic scraping functionality for Twitter/X posts via Nitter instances.
- Integration with Perplexity AI for factual report generation.
- Structured JSON output for scraped data and analysis.
- Interactive CLI mode and command-line operations.
- Environment variable configuration support.

## Notes

- Dates and version numbers are placeholders and should be updated based on actual release timelines.
- Future changes will be documented under the `[Unreleased]` section until a new version is released.
