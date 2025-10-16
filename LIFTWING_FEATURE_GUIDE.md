# LiftWing Model Visualization Feature - Implementation Guide

## 📋 Overview

This document describes the completed LiftWing model visualization feature for PendingChangesBot-ng. The feature allows users to visualize how LiftWing machine learning models evaluate Wikipedia articles over their revision history.

## ✅ Completed Features

### 1. **Bug Fixes** ✅
- Fixed undefined `headers` variable in `fetch_predictions` view
- Cleaned up duplicate code in views.py
- Improved error handling across all endpoints

### 2. **Frontend Visualization** ✅
- **Modern UI** with responsive design
- **Interactive Line Chart** using Chart.js showing model scores over revision history
- **Revision History Table** with clickable revision IDs linking to Wikipedia diffs
- **Loading Indicators** with progress bar for batch processing
- **Error Handling** with user-friendly status messages
- **Multi-wiki Support** for 6+ Wikipedia language editions

### 3. **Backend API Improvements** ✅
- **Article Validation** - Real MediaWiki API integration to verify article existence
- **Revision History Fetching** - Complete revision data with metadata
- **LiftWing Integration** - Direct API calls to LiftWing prediction service
- **Batch Processing** - Efficient handling of multiple revisions (10 at a time)
- **Flexible rev_id Support** - Can use specific revision ID or fetch latest

### 4. **Database Models** ✅
Added two new models for caching:

#### `LiftWingPrediction`
Caches LiftWing model predictions to avoid redundant API calls.
- Fields: wiki, revid, model_name, prediction_class, prediction_data
- Expires after 24 hours
- Indexed for fast lookups

#### `ArticleRevisionHistory`
Caches complete revision history for articles.
- Fields: wiki, pageid, title, revid, parentid, user, timestamp, comment, size
- Indexed by wiki, pageid, revid, and timestamp

### 5. **Admin Interface** ✅
- Both new models registered in Django admin
- Searchable and filterable
- Read-only timestamp fields

---

## 🚀 Setup Instructions

### Step 1: Run Database Migrations

```bash
cd app
python manage.py makemigrations
python manage.py migrate
```

### Step 2: Start the Development Server

```bash
cd app
python manage.py runserver
```

### Step 3: Access the Feature

Open your browser and navigate to:
```
http://127.0.0.1:8000/liftwing/
```

---

## 🧪 Testing Guide

### Test Case 1: Basic Article Analysis

1. **Select Wiki:** English Wikipedia
2. **Article Title:** `Python (programming language)`
3. **Model:** Article Quality
4. **Click:** "📊 Analyze Article"

**Expected Results:**
- ✅ Article validation succeeds
- ✅ Revision history fetched (up to 20 revisions)
- ✅ Progress bar shows loading status
- ✅ Line chart displays quality scores over time
- ✅ Table shows revision details with clickable links

### Test Case 2: Different Wikis

Test with multiple wikis:
- **German Wikipedia (de):** `Berlin`
- **French Wikipedia (fr):** `Paris`
- **Hindi Wikipedia (hi):** `भारत` (India)
- **Finnish Wikipedia (fi):** `Suomi` (Finland)

### Test Case 3: Invalid Article

1. **Article Title:** `ThisArticleDoesNotExist123456`
2. **Click:** "📊 Analyze Article"

**Expected Results:**
- ❌ Error message: "Article not found"

### Test Case 4: Different Models

Test both available models:
- **Article Quality** - Predicts quality class (FA, GA, B, C, Start, Stub)
- **Draft Quality** - Evaluates draft articles

---

## 📊 How It Works

### Workflow

```
1. User enters article title
   ↓
2. Validate article exists (MediaWiki API)
   ↓
3. Fetch revision history (up to 20 latest revisions)
   ↓
4. For each revision:
   - Call LiftWing API for prediction
   - Process in batches of 10
   - Update progress bar
   ↓
5. Display results:
   - Line chart with quality scores
   - Table with revision metadata
```

### API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/validate_article/` | POST | Validate article exists on wiki |
| `/fetch_revisions/` | POST | Get complete revision history |
| `/fetch_predictions/` | POST | Get LiftWing model predictions |
| `/liftwing/` | GET | Main visualization page |

---

## 🔧 Technical Details

### Chart Visualization

The line chart maps quality predictions to numeric values:

```javascript
Quality Mapping:
FA (Featured Article) = 6
GA (Good Article) = 5
B (B-class) = 4
C (C-class) = 3
Start (Start-class) = 2
Stub (Stub-class) = 1
```

### Batch Processing

Revisions are processed in batches of 10 to:
- Avoid overwhelming the LiftWing API
- Provide real-time progress feedback
- Handle large revision histories efficiently

### Error Handling

All API calls include:
- Try-catch blocks
- Timeout settings (10 seconds)
- User-friendly error messages
- Graceful degradation

---

## 📝 Files Modified/Created

### Modified Files
1. `app/reviews/views.py`
   - Fixed `fetch_predictions` bug
   - Added support for rev_id parameter
   - Improved error handling

2. `app/reviews/models.py`
   - Added `LiftWingPrediction` model
   - Added `ArticleRevisionHistory` model

3. `app/reviews/admin.py`
   - Registered new models

4. `app/templates/reviews/lift.html`
   - Complete redesign with modern UI
   - Chart.js line chart implementation
   - Revision history table
   - Loading indicators
   - Error handling

---

## 🎯 Next Steps (Optional Enhancements)

### Immediate
- [ ] Test with actual Wikipedia articles
- [ ] Verify LiftWing API responses
- [ ] Test error scenarios

### Future Enhancements
1. **Caching Implementation**
   - Check database before API calls
   - Store predictions in `LiftWingPrediction` table
   - Implement cache invalidation

2. **Pagination**
   - Handle articles with 1000+ revisions
   - Add "Load More" button
   - Implement lazy loading

3. **Multiple Models**
   - Support selecting multiple models simultaneously
   - Show multiple lines on chart
   - Compare model predictions

4. **Diff Viewer**
   - Embed diff view below chart when clicking revision
   - Highlight changes
   - Similar to autoreview feature

5. **Export Features**
   - Download data as CSV/JSON
   - Export chart as image
   - Generate reports

6. **Advanced Filtering**
   - Filter by date range
   - Filter by user
   - Filter by prediction class

---

## 🐛 Known Limitations

1. **Revision Limit:** Currently processes only the latest 20 revisions for demo purposes
2. **API Rate Limits:** LiftWing API may have rate limits (handled with batch processing)
3. **Model Availability:** Not all models are available for all wikis
4. **Cache Not Implemented:** Database models created but not yet integrated with views

---

## 📚 Resources

- [LiftWing Models Documentation](https://meta.wikimedia.org/wiki/Machine_learning_models)
- [Article Quality Model](https://meta.wikimedia.org/wiki/Machine_learning_models/Production/Language-agnostic_Wikipedia_article_quality)
- [MediaWiki API](https://www.mediawiki.org/wiki/API:Main_page)
- [Chart.js Documentation](https://www.chartjs.org/docs/latest/)

---

## 🤝 Contributors

- **Nirmeet Kamble** - Initial implementation and PR #83
- **Ambati Teja Sri Surya** - Article validation, testing, and enhancements

---

## 📞 Support

For issues or questions:
1. Check the [CONTRIBUTING.md](CONTRIBUTING.md) guide
2. Open an issue on GitHub
3. Review existing PR #83 discussions

---

**Status:** ✅ Ready for Testing and Review

Last Updated: October 16, 2025

