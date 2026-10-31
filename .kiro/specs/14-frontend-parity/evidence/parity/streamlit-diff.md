Events: events.parquet, 45283 rows, journey user_onboarding.

| Step | Engine window | Users (Streamlit) | Unique users (engine) | Errors (Streamlit count) | Error rate % (engine) | Dwell s (Streamlit) | Dwell s (engine) | Friction (Streamlit fallback, critical >50) | Friction (engine, critical >= 60) |
|---|---|---|---|---|---|---|---|---|---|
| landing_page | api_default_30d | 1489 | 1489 | 45 | 3.02 | 3.2 | 5.2 | 9.2 (not critical) | 31 (not critical) |
| landing_page | all_data_365d | 1489 | 1489 | 45 | 3.02 | 3.2 | 5.2 | 9.2 (not critical) | 31 (not critical) |
| sign_up_form | api_default_30d | 1335 | 1335 | 296 | 22.17 | 6.2 | 19.1 | 22.3 (not critical) | 72 (critical) |
| sign_up_form | all_data_365d | 1335 | 1335 | 296 | 22.17 | 6.2 | 19.1 | 22.3 (not critical) | 72 (critical) |
| email_verification | api_default_30d | 1037 | 1037 | 498 | 48.02 | 29.7 | 67.1 | 40.5 (not critical) | 90 (critical) |
| email_verification | all_data_365d | 1037 | 1037 | 498 | 48.02 | 29.7 | 67.1 | 40.5 (not critical) | 90 (critical) |
| profile_setup | api_default_30d | 654 | 654 | 59 | 9.02 | 6.1 | 26.6 | 13.2 (not critical) | 54 (not critical) |
| profile_setup | all_data_365d | 654 | 654 | 59 | 9.02 | 6.1 | 26.6 | 13.2 (not critical) | 54 (not critical) |
| plan_selection | api_default_30d | 531 | 531 | 42 | 7.91 | 11.8 | 36.7 | 15.4 (not critical) | 63 (critical) |
| plan_selection | all_data_365d | 531 | 531 | 42 | 7.91 | 11.8 | 36.7 | 15.4 (not critical) | 63 (critical) |
| payment_info | api_default_30d | 387 | 387 | 76 | 19.64 | 13.6 | 46.3 | 25.0 (not critical) | 85 (critical) |
| payment_info | all_data_365d | 387 | 387 | 76 | 19.64 | 13.6 | 46.3 | 25.0 (not critical) | 85 (critical) |
| confirm_details | api_default_30d | 248 | 248 | 7 | 2.82 | 5.4 | 9.5 | 4.2 (not critical) | 17 (not critical) |
| confirm_details | all_data_365d | 248 | 248 | 7 | 2.82 | 5.4 | 9.5 | 4.2 (not critical) | 17 (not critical) |
| onboarding_done | api_default_30d | 234 | 234 | 2 | 0.85 | 2.5 | 3.9 | 1.6 (not critical) | 5 (not critical) |
| onboarding_done | all_data_365d | 234 | 234 | 2 | 0.85 | 2.5 | 3.9 | 1.6 (not critical) | 5 (not critical) |
