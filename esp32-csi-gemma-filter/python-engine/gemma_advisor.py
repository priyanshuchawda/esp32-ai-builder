import json
import logging
import requests
import config

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised only before deps install
    genai = None
    types = None

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a local Wi-Fi CSI noise filtering advisor.
You do not directly filter raw samples.
You only choose the best filter and parameters from summary statistics.
Return JSON only.
No markdown.
No explanation outside JSON.

Allowed filters:
- moving_average
- median
- hampel
- lowpass
- none

Required JSON response format:
{
  "filter": "median",
  "window_size": 5,
  "outlier_threshold": 3.0,
  "lowpass_alpha": 0.25,
  "confidence": 0.82,
  "reason": "High outlier ratio suggests spike noise, so median filtering is best."
}"""


def get_rule_based_decision(features: dict) -> dict:
    """
    Local rule-based fallback decision generator.
    """
    outlier_ratio = features.get("outlier_ratio", 0.0)
    signal_std = features.get("signal_std", 0.0)

    if outlier_ratio > config.FALLBACK_OUTLIER_RATIO_THRESHOLD:
        return {
            "filter": "median",
            "window_size": 5,
            "outlier_threshold": 3.0,
            "lowpass_alpha": 0.25,
            "confidence": 1.0,
            "reason": f"Rule-based fallback: high outlier ratio detected ({outlier_ratio:.2f} > {config.FALLBACK_OUTLIER_RATIO_THRESHOLD:.2f})",
        }
    elif signal_std > config.FALLBACK_HIGH_STD_THRESHOLD:
        return {
            "filter": "moving_average",
            "window_size": 7,
            "outlier_threshold": 3.0,
            "lowpass_alpha": 0.25,
            "confidence": 1.0,
            "reason": f"Rule-based fallback: high signal standard deviation ({signal_std:.2f} > {config.FALLBACK_HIGH_STD_THRESHOLD:.2f})",
        }
    elif signal_std > config.FALLBACK_NOISE_STD_THRESHOLD:
        return {
            "filter": "lowpass",
            "window_size": 5,
            "outlier_threshold": 3.0,
            "lowpass_alpha": 0.25,
            "confidence": 1.0,
            "reason": f"Rule-based fallback: smooth but noisy signal detected (std: {signal_std:.2f})",
        }
    else:
        return {
            "filter": "none",
            "window_size": 5,
            "outlier_threshold": 3.0,
            "lowpass_alpha": 0.25,
            "confidence": 1.0,
            "reason": "Rule-based fallback: signal is clean, no filter needed",
        }


def cleanse_json_response(text: str) -> str:
    """
    Cleanses markdown block tags (e.g. ```json) from the response text.
    """
    text = text.strip()
    # Remove markdown code block wrappers if Gemma adds them
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_advisor_decision(text: str) -> dict | None:
    clean_content = cleanse_json_response(text)
    decision = json.loads(clean_content)
    required_keys = [
        "filter",
        "window_size",
        "outlier_threshold",
        "lowpass_alpha",
        "confidence",
        "reason",
    ]
    if all(key in decision for key in required_keys):
        return decision
    logger.warning("Gemma response JSON missing keys. Response: %s", decision)
    return None


def build_advisor_prompt(features: dict) -> str:
    return (
        "Here are the summary features of the current signal window:\n"
        f"{json.dumps(features, indent=2)}\n\n"
        "Recommend the best filter and parameters."
    )


def query_gemini_advisor(features: dict, client_factory=None) -> dict:
    """
    Queries hosted Gemma 4 through the Gemini API with current features.
    Falls back to rule-based decision if anything fails.
    """
    if not config.GEMINI_API_KEY:
        logger.info("GEMINI_API_KEY is not set. Falling back to local rule-based advisor.")
        return get_rule_based_decision(features)

    if genai is None or types is None:
        logger.warning("google-genai is not installed. Falling back to local rule-based advisor.")
        return get_rule_based_decision(features)

    try:
        logger.info(
            "Querying hosted Gemma model '%s' through the Gemini API...",
            config.GEMINI_GEMMA_MODEL,
        )
        client = client_factory() if client_factory else genai.Client(api_key=config.GEMINI_API_KEY)
        thinking_config = None
        if config.GEMINI_THINKING_LEVEL:
            thinking_config = types.ThinkingConfig(
                thinking_level=config.GEMINI_THINKING_LEVEL
            )
        response = client.models.generate_content(
            model=config.GEMINI_GEMMA_MODEL,
            contents=build_advisor_prompt(features),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.0,
                response_mime_type="application/json",
                thinking_config=thinking_config,
            ),
        )

        decision = parse_advisor_decision(response.text or "")
        if decision is not None:
            logger.info(
                "Successfully received hosted Gemma advice: %s filter selected.",
                decision["filter"],
            )
            return decision
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse hosted Gemma output as JSON: %s", e)
    except Exception as e:
        logger.warning("Unexpected error when querying hosted Gemma: %s", e)

    logger.info("Falling back to local rule-based advisor.")
    return get_rule_based_decision(features)


def query_ollama_advisor(features: dict) -> dict:
    """
    Queries local Ollama API running Gemma with current features.
    Falls back to rule-based decision if anything fails.
    """
    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_advisor_prompt(features)},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }

    try:
        logger.info(
            f"Querying local Gemma model '{config.OLLAMA_MODEL}' at {config.OLLAMA_URL}..."
        )
        response = requests.post(
            config.OLLAMA_URL,
            json=payload,
            timeout=config.OLLAMA_TIMEOUT_SECONDS,
        )

        if response.status_code == 200:
            result_json = response.json()
            message_content = result_json.get("message", {}).get("content", "")

            logger.debug(f"Gemma Raw Output: {message_content}")

            decision = parse_advisor_decision(message_content)
            if decision is not None:
                logger.info(
                    f"Successfully received Gemma advice: {decision['filter']} filter selected."
                )
                return decision
        else:
            logger.warning(f"Ollama returned HTTP error status: {response.status_code}")

    except requests.exceptions.RequestException as e:
        logger.warning(f"Ollama API connection failed (is Ollama running?): {e}")
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse Gemma output as JSON: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error when querying Gemma: {e}")

    logger.info("Falling back to local rule-based advisor.")
    return get_rule_based_decision(features)


def query_gemma_advisor(features: dict) -> dict:
    if config.GEMMA_ADVISOR_PROVIDER == "ollama":
        return query_ollama_advisor(features)
    return query_gemini_advisor(features)
