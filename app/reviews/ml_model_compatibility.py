"""
ML Model Language Compatibility Matrix.

This module defines which ML models are compatible with which wiki languages.
Based on Wikimedia ML model documentation:
- https://meta.wikimedia.org/wiki/Machine_learning_models/Production/Multilingual_revert_risk
- https://meta.wikimedia.org/wiki/Machine_learning_models/Production/Language-agnostic_revert_risk
- https://meta.wikimedia.org/wiki/ORES
"""

# Multilingual Revert Risk: 47 supported languages
MULTILINGUAL_REVERT_RISK_LANGUAGES = [
    "ar", "bg", "bn", "ca", "cs", "da", "de", "el", "en", "es", "et", "eu",
    "fa", "fi", "fr", "gl", "he", "hi", "hr", "hu", "hy", "id", "it", "ja",
    "ka", "ko", "lt", "lv", "mk", "ml", "ms", "my", "nl", "nn", "no", "pl",
    "pt", "ro", "ru", "simple", "sk", "sl", "sq", "sr", "sv", "ta", "th",
    "tr", "uk", "ur", "vi", "zh"
]

# Language-Agnostic Revert Risk: supports ALL 250+ Wikipedia languages
# Returns true for all languages
LANGUAGE_AGNOSTIC_REVERT_RISK_ALL = True

# ORES damaging/goodfaith: Limited language support
# Based on https://ores.wikimedia.org/v3/scores/
ORES_DAMAGING_GOODFAITH_LANGUAGES = [
    "ar", "ca", "cs", "de", "en", "es", "et", "eu", "fa", "fi", "fr", "gl",
    "he", "hu", "id", "it", "ja", "ko", "nl", "no", "pl", "pt", "ro", "ru",
    "simple", "sq", "sr", "sv", "tr", "uk", "vi", "zh"
]

# Lift Wing damaging/goodfaith: Similar to multilingual models
# Using same language list as multilingual revert risk
LIFTWING_DAMAGING_GOODFAITH_LANGUAGES = MULTILINGUAL_REVERT_RISK_LANGUAGES

# Article Quality/Topic: Language-specific models, varies by wiki
# These require per-wiki configuration
ARTICLE_QUALITY_TOPIC_WIKI_SPECIFIC = True


def is_model_compatible(model_type: str, wiki_language: str) -> bool:
    """
    Check if a model type is compatible with a wiki language.

    Args:
        model_type: Type of ML model (e.g., 'revertrisk', 'damaging', 'goodfaith')
        wiki_language: Wiki language code (e.g., 'en', 'fi', 'hu')

    Returns:
        True if the model is compatible with the language, False otherwise
    """
    model_type = model_type.lower()
    wiki_language = wiki_language.lower()

    # Language-agnostic revert risk works for ALL languages
    if model_type in ["revertrisk", "revertrisk_language_agnostic"]:
        return True

    # Multilingual revert risk: 47 languages
    if model_type == "revertrisk_multilingual":
        return wiki_language in MULTILINGUAL_REVERT_RISK_LANGUAGES

    # ORES models: limited support
    if model_type in ["ores_damaging", "ores_goodfaith"]:
        return wiki_language in ORES_DAMAGING_GOODFAITH_LANGUAGES

    # Lift Wing damaging/goodfaith: broader support
    if model_type in ["damaging", "goodfaith"]:
        return wiki_language in LIFTWING_DAMAGING_GOODFAITH_LANGUAGES

    # Article quality and topic are wiki-specific
    if model_type in ["articlequality", "articletopic"]:
        # These need per-wiki API testing
        # For now, return False to be safe
        return False

    # Unknown model type
    return False


def get_compatible_models(wiki_language: str) -> list[str]:
    """
    Get list of compatible models for a given wiki language.

    Args:
        wiki_language: Wiki language code (e.g., 'en', 'fi', 'hu')

    Returns:
        List of compatible model types
    """
    wiki_language = wiki_language.lower()
    compatible = []

    # Language-agnostic revert risk always compatible
    compatible.append("revertrisk_language_agnostic")

    # Check multilingual revert risk
    if wiki_language in MULTILINGUAL_REVERT_RISK_LANGUAGES:
        compatible.append("revertrisk_multilingual")

    # Check ORES models
    if wiki_language in ORES_DAMAGING_GOODFAITH_LANGUAGES:
        compatible.extend(["ores_damaging", "ores_goodfaith"])

    # Check Lift Wing damaging/goodfaith
    if wiki_language in LIFTWING_DAMAGING_GOODFAITH_LANGUAGES:
        compatible.extend(["damaging", "goodfaith"])

    return compatible


def get_incompatibility_reason(model_type: str, wiki_language: str) -> str | None:
    """
    Get human-readable reason why a model is incompatible with a language.

    Args:
        model_type: Type of ML model
        wiki_language: Wiki language code

    Returns:
        Reason string if incompatible, None if compatible
    """
    if is_model_compatible(model_type, wiki_language):
        return None

    model_type = model_type.lower()
    wiki_language = wiki_language.lower()

    if model_type == "revertrisk_multilingual":
        return (
            f"Multilingual revert risk model does not support '{wiki_language}'. "
            f"It only supports 47 languages. Use language-agnostic revert risk instead."
        )

    if model_type in ["ores_damaging", "ores_goodfaith"]:
        return (
            f"ORES {model_type.split('_')[1]} model does not support '{wiki_language}'. "
            f"Consider using Lift Wing models instead."
        )

    if model_type in ["damaging", "goodfaith"]:
        return (
            f"Lift Wing {model_type} model does not support '{wiki_language}'. "
            f"This model supports 47 languages."
        )

    return f"Model '{model_type}' is not supported for language '{wiki_language}'."
