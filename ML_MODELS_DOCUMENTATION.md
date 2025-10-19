# Multi-Model ML Support Documentation

## Overview

PendingChangesBot-ng now supports multiple Wikimedia ML models for auto-review decisions, not just the revertrisk model. This allows wikis to choose which model(s) work best for their language and use case.

## Available ML Models

The following Wikimedia ML models are supported:

### 1. **Revert Risk (revertrisk)** - Language-agnostic
- **Endpoint**: `revertrisk-language-agnostic:predict`
- **Description**: Predicts the probability that an edit will be reverted
- **Best for**: All languages, general-purpose revert prediction
- **Score meaning**: Higher score = higher probability of being reverted

### 2. **Damaging Edit Detection (damaging)**
- **Endpoint**: `damaging:predict`
- **Description**: Detects edits that are damaging to the article
- **Best for**: Languages with extensive training data (English, German, French, etc.)
- **Score meaning**: Higher score = more likely to be damaging

### 3. **Good Faith Prediction (goodfaith)**
- **Endpoint**: `goodfaith:predict`
- **Description**: Predicts whether an edit was made in good faith
- **Best for**: Languages with good training data
- **Score meaning**: Higher score = LESS good faith (more likely bad faith)
- **Note**: Uses `probabilities.false` (inverted score)

### 4. **Article Quality Assessment (articlequality)**
- **Endpoint**: `articlequality:predict`
- **Description**: Assesses the quality of an article
- **Best for**: Major wikis with article quality ratings
- **Score meaning**: Predicts article quality class (stub, start, C, B, GA, FA)
- **Note**: Currently extracts `probabilities.stub` as a low-quality indicator

### 5. **Article Topic Classification (articletopic)**
- **Endpoint**: `articletopic:predict`
- **Description**: Classifies the topic of an article
- **Best for**: Topic-based filtering or analysis
- **Note**: Requires special handling (not yet fully implemented)

## Configuration

### Database Schema

Two new fields have been added to `WikiConfiguration`:

```python
ml_model_type = models.CharField(
    max_length=50,
    default='revertrisk',
    choices=[...],
    help_text="Which Wikimedia ML model to use for this wiki"
)

ml_model_threshold = models.FloatField(
    default=0.0,
    help_text="Threshold for ML model score (0.0-1.0). "
              "Edits with a score above this threshold will not be auto-approved. "
              "Set to 0.0 to disable ML model checking."
)
```

### Backward Compatibility

The legacy `revertrisk_threshold` field is maintained for backward compatibility:
- Existing configurations will continue to work
- If `ml_model_threshold` is 0.0, the system falls back to `revertrisk_threshold`
- The `revertrisk_threshold` field is now marked as DEPRECATED

## Usage

### Via Django Admin

1. Navigate to the Django admin interface
2. Select a `WikiConfiguration` object
3. Set `ml_model_type` to your preferred model
4. Set `ml_model_threshold` to your desired threshold (0.0-1.0)
5. Save the configuration

### Via Web UI

1. Open the PendingChangesBot-ng web interface
2. Select a wiki from the dropdown
3. Click "Show" to expand the configuration section
4. Select the ML model type from the dropdown
5. Enter a threshold value (0.0 to disable, or a value between 0.0-1.0)
6. Click "Save configuration"

### Via API

Send a PUT request to `/api/wikis/{wiki_id}/configuration/`:

```json
{
  "ml_model_type": "damaging",
  "ml_model_threshold": 0.7
}
```

Response:
```json
{
  "blocking_categories": [...],
  "auto_approved_groups": [...],
  "ml_model_type": "damaging",
  "ml_model_threshold": 0.7
}
```

## How It Works

### Backend Processing

1. When an edit is being auto-reviewed, the system checks the `ml_model_threshold`
2. If threshold > 0.0, it queries the Wikimedia ML API with the configured model type
3. The API returns a probability score (0.0-1.0)
4. If the score exceeds the threshold, the edit is BLOCKED from auto-approval
5. If the API call fails, the system fails open (does not block approval)

### ML Model Configuration

Model configurations are defined in `autoreview.py`:

```python
ML_MODEL_CONFIGS = {
    'revertrisk': {
        'endpoint': 'revertrisk-language-agnostic:predict',
        'probability_key': 'true',
        'description': 'Language-agnostic revert risk prediction',
    },
    'damaging': {
        'endpoint': 'damaging:predict',
        'probability_key': 'true',
        'description': 'Damaging edit detection',
    },
    # ... more models
}
```

### API Integration

The generic `_get_ml_model_score()` function handles all ML models:

```python
def _get_ml_model_score(revision: PendingRevision, model_type: str = 'revertrisk') -> float | None:
    """
    Query the Wikimedia ML API to get a score for an edit using the specified model.

    Returns:
        The ML model score (0.0-1.0) or None if the API call fails
    """
```

## Recommended Thresholds

Based on Wikimedia's ML model documentation:

- **revertrisk**: 0.5 - 0.7 (conservative to moderate)
- **damaging**: 0.6 - 0.8 (moderate to strict)
- **goodfaith**: 0.3 - 0.5 (lower values for stricter filtering)
- **articlequality**: Varies by use case

**Important**: These are starting points. Each wiki should test and adjust thresholds based on their specific needs and false positive/negative rates.

## Testing Different Models

To compare different models on your wiki:

1. Start with a low threshold (e.g., 0.3) to see score distributions
2. Review blocked edits to identify false positives
3. Review auto-approved edits to identify false negatives
4. Adjust the threshold iteratively
5. Consider switching models if performance is poor

## Implementation Details

### Files Modified

1. **app/reviews/models.py**: Added `ml_model_type` and `ml_model_threshold` fields
2. **app/reviews/autoreview.py**:
   - Added `ML_MODEL_CONFIGS` dictionary
   - Created `_get_ml_model_score()` function
   - Updated Test 8 to use generic ML models
3. **app/reviews/views.py**: Updated API to expose ML model configuration
4. **app/static/reviews/app.js**: Added ML model selection to Vue.js app
5. **app/templates/reviews/index.html**: Added UI elements for model selection
6. **app/reviews/migrations/0009_add_ml_model_fields.py**: Database migration

### Test Coverage

New test file: `app/reviews/tests/test_ml_models.py`

Tests cover:
- ML model disabled when threshold is 0.0
- High scores blocking approval (damaging model)
- Low good faith scores blocking approval
- API failures failing open (not blocking)
- Backward compatibility with `revertrisk_threshold`
- Direct `_get_ml_model_score()` function testing

## Future Enhancements

### Potential Features

1. **Multiple simultaneous models**: Check BOTH revertrisk AND damaging
2. **Automatic model selection**: Based on wiki language/size
3. **Fallback models**: If primary model API fails, try secondary
4. **Per-model thresholds**: Different thresholds for different models
5. **Topic-based filtering**: Use articletopic to filter specific topics
6. **Quality-based auto-approval**: Use articlequality to auto-approve high-quality edits

### Questions for Discussion

1. Should we support checking multiple models simultaneously?
2. Should thresholds be per-model or global?
3. Should we implement automatic model selection based on wiki language?
4. Should there be a fallback model if the primary model API fails?

## References

- [Wikimedia Machine Learning Models](https://meta.wikimedia.org/wiki/Machine_learning_models)
- [Lift Wing API Documentation](https://api.wikimedia.org/wiki/Lift_Wing_API)
- [ORES (Legacy) Documentation](https://www.mediawiki.org/wiki/ORES)

## Related Issues

- Issue #90: Add support for multiple Wikimedia ML models
- PR #45: Implements revertrisk (initial implementation)
- Issue #18: Original ML integration request

## Migration Guide

### For Existing Deployments

1. Run the migration:
   ```bash
   python manage.py migrate reviews 0009_add_ml_model_fields
   ```

2. Existing `revertrisk_threshold` configurations will continue to work
3. To use new models, update configurations via admin or API
4. No action required if you want to keep using revertrisk

### For New Deployments

1. Run all migrations
2. Configure ML model type and threshold via admin or API
3. Default is `revertrisk` with threshold 0.0 (disabled)

## Troubleshooting

### ML check always shows "disabled"
- Check that `ml_model_threshold` > 0.0
- Verify the model type is valid

### API failures / "Failed to fetch score"
- Check network connectivity to Wikimedia API
- Verify the wiki code and family are correct
- Check Wikimedia API status at https://api.wikimedia.org/

### Scores seem incorrect
- Verify you're using the correct probability key for your model
- Check the model documentation for score interpretation
- Test with known revisions to validate behavior

## Contributing

To add support for a new ML model:

1. Add model configuration to `ML_MODEL_CONFIGS` in `autoreview.py`
2. Add choice to `ml_model_type` field in `models.py`
3. Add option to dropdown in `templates/reviews/index.html`
4. Add tests in `test_ml_models.py`
5. Update this documentation

---

**Last Updated**: 2025-10-19
**Authors**: @kobinna, @xenacode-art
**Status**: Implemented, ready for testing
