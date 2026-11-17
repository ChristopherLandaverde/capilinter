# Synthetic Dataset Quality API responses

Shaped after the sample responses on Meta's Dataset Quality API page
(https://developers.facebook.com/docs/marketing-api/conversions-api/dataset-quality-api).
Every value is made up. No real dataset, account or token was used.

- `dataset_quality_healthy.json`: one event, nothing to flag.
- `dataset_quality_issues.json`: EMQ below 6.0 with a Meta diagnostic (Purchase),
  event coverage below goal (Lead), server events missing the dedup key (AddToCart).
- `api_error_invalid_token.json`: Graph API error body for an invalid token (code 190).
