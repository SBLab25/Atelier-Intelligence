import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from settings import get_settings

logger = logging.getLogger(__name__)

def _log_retry(retry_state):
    if retry_state.attempt_number > 1:
        logger.warning(f"Retrying LLM call. Attempt {retry_state.attempt_number}. Exception: {retry_state.outcome.exception()}")

_POLICY = get_settings().llm.retry   # CJI_LLM_RETRY_ATTEMPTS / _MIN_S / _MAX_S (Spec 04)

llm_retry = retry(
    stop=stop_after_attempt(_POLICY.attempts),
    wait=wait_exponential(multiplier=1, min=_POLICY.min_wait_s, max=_POLICY.max_wait_s),
    retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout)),
    after=_log_retry,
    reraise=True
)
