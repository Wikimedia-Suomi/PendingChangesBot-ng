# LiftWing Feature - Quick Test Checklist

## 🚦 Pre-Testing Setup

### 1. Database Migrations
```bash
cd app
python manage.py makemigrations
python manage.py migrate
```

**Expected Output:**
```
Migrations for 'reviews':
  reviews/migrations/0008_liftwingprediction_articlerevisionhistory.py
    - Create model LiftWingPrediction
    - Create model ArticleRevisionHistory
```

### 2. Start Server
```bash
python manage.py runserver
```

**Expected Output:**
```
Starting development server at http://127.0.0.1:8000/
```

---

## ✅ Test Scenarios

### Test 1: Page Loads Correctly

**Steps:**
1. Navigate to `http://127.0.0.1:8000/liftwing/`

**✅ Success Criteria:**
- Page loads without errors
- UI shows:
  - Wiki dropdown (6 options)
  - Article title input field
  - Model dropdown (2 options)
  - "Analyze Article" button
  - Empty chart area
  - Empty table area

---

### Test 2: Article Validation - Valid Article

**Steps:**
1. Select: **English Wikipedia**
2. Enter: `Earth`
3. Select: **Article Quality**
4. Click: **📊 Analyze Article**

**✅ Success Criteria:**
- Status shows: "🔍 Validating article..."
- Status changes to: "✅ Article found: Earth"
- Status shows: "📥 Fetching revision history..."
- Progress bar appears and updates
- Status shows: "✅ Analysis complete!"
- Chart appears with line graph
- Table appears with ~20 revisions

**⏱️ Expected Time:** 10-30 seconds

---

### Test 3: Article Validation - Invalid Article

**Steps:**
1. Select: **English Wikipedia**
2. Enter: `ThisArticleTotallyDoesNotExist12345XYZ`
3. Click: **📊 Analyze Article**

**✅ Success Criteria:**
- Status shows: "🔍 Validating article..."
- Status shows error: "❌ Article 'ThisArticleTotallyDoesNotExist12345XYZ' not found on en.wikipedia.org"
- No chart appears
- No table appears

**⏱️ Expected Time:** 1-2 seconds

---

### Test 4: Different Wiki

**Steps:**
1. Select: **German Wikipedia**
2. Enter: `Berlin`
3. Select: **Article Quality**
4. Click: **📊 Analyze Article**

**✅ Success Criteria:**
- Article validated successfully
- Revisions fetched
- Chart shows quality progression
- Table shows German user comments

---

### Test 5: Chart Interaction

**Steps:**
1. After successful analysis, hover over chart points

**✅ Success Criteria:**
- Tooltip appears showing:
  - Prediction class (e.g., "Prediction: C")
  - Timestamp of revision
- Chart is responsive (resizes with window)

---

### Test 6: Table Functionality

**Steps:**
1. After successful analysis, click on a revision ID in the table

**✅ Success Criteria:**
- Opens new tab with Wikipedia diff view
- Shows the specific revision changes

---

### Test 7: Multiple Analyses

**Steps:**
1. Analyze `Python (programming language)`
2. Wait for completion
3. Analyze `JavaScript`
4. Wait for completion

**✅ Success Criteria:**
- Second analysis replaces first chart/table
- No JavaScript errors in console
- Previous chart is properly destroyed

---

### Test 8: Loading States

**Steps:**
1. Start analysis of any article
2. Observe UI during loading

**✅ Success Criteria:**
- Button text changes to "⏳ Analyzing..."
- Button becomes disabled (can't click again)
- Progress bar appears and updates from 0% to 100%
- Status messages update in real-time
- After completion, button returns to "📊 Analyze Article"

---

### Test 9: Error Handling - Network Issue

**Steps:**
1. Disconnect internet (or use DevTools to simulate offline)
2. Try to analyze an article

**✅ Success Criteria:**
- Error message appears
- Button re-enables
- No crashes

---

### Test 10: Console Check

**Steps:**
1. Open browser DevTools (F12)
2. Go to Console tab
3. Perform any analysis

**✅ Success Criteria:**
- No JavaScript errors
- No 404 errors
- API calls visible in Network tab
- Responses are valid JSON

---

## 🔍 API Endpoint Tests

### Test Direct API Calls

#### 1. Validate Article
```bash
curl -X POST http://127.0.0.1:8000/validate_article/ \
  -H "Content-Type: application/json" \
  -d '{"wiki": "en", "article": "Earth"}'
```

**Expected Response:**
```json
{
  "valid": true,
  "exists": true,
  "missing": false,
  "pageid": 9228,
  "normalized_title": "Earth",
  "error": null
}
```

#### 2. Fetch Revisions
```bash
curl -X POST http://127.0.0.1:8000/fetch_revisions/ \
  -H "Content-Type: application/json" \
  -d '{"wiki": "en", "article": "Earth"}'
```

**Expected Response:**
```json
{
  "title": "Earth",
  "revisions": [
    {
      "revid": 123456,
      "timestamp": "2024-10-01T12:00:00Z",
      "user": "ExampleUser",
      "comment": "Updated content"
    },
    ...
  ]
}
```

---

## 🐛 Troubleshooting

### Issue: Page shows 404
**Solution:** Check that URL routes are configured in `urls.py`

### Issue: "CSRF token missing"
**Solution:** Ensure Django session middleware is enabled

### Issue: LiftWing API errors
**Solution:** 
- Check internet connection
- Verify LiftWing API is accessible
- Try a different article/model

### Issue: Slow loading
**Solution:**
- Normal for first run (API calls take time)
- Check Network tab for slow endpoints
- LiftWing API can be slow for some models

### Issue: Chart doesn't appear
**Solution:**
- Check browser console for JS errors
- Verify Chart.js CDN is loading
- Ensure data structure is correct

---

## 📊 Sample Test Articles

### Quick Tests (Fast loading, stable)
- **English:** `Earth`, `Moon`, `Sun`
- **German:** `Berlin`, `Deutschland`
- **French:** `Paris`, `France`

### Medium Tests (Good revision history)
- **English:** `Python (programming language)`, `JavaScript`, `HTML`
- **Hindi:** `भारत` (India)

### Stress Tests (Many revisions, slower)
- **English:** `United States`, `World War II`

---

## ✅ Final Checklist

Before marking as complete:

- [ ] All 10 UI tests pass
- [ ] API endpoints respond correctly
- [ ] No console errors
- [ ] Chart displays properly
- [ ] Table is populated correctly
- [ ] Links work
- [ ] Loading states work
- [ ] Error handling works
- [ ] Multiple wikis work
- [ ] Database migrations applied successfully

---

## 📝 Test Results Template

```markdown
## Test Results - [Your Name]

**Date:** [Date]
**Environment:** Windows/Mac/Linux - Browser: Chrome/Firefox/Safari

### Tests Passed: X/10

| Test | Status | Notes |
|------|--------|-------|
| Test 1: Page Loads | ✅/❌ | |
| Test 2: Valid Article | ✅/❌ | |
| Test 3: Invalid Article | ✅/❌ | |
| Test 4: Different Wiki | ✅/❌ | |
| Test 5: Chart Interaction | ✅/❌ | |
| Test 6: Table Links | ✅/❌ | |
| Test 7: Multiple Analyses | ✅/❌ | |
| Test 8: Loading States | ✅/❌ | |
| Test 9: Error Handling | ✅/❌ | |
| Test 10: Console Check | ✅/❌ | |

### Issues Found:
1. [Describe issue]
2. [Describe issue]

### Additional Notes:
[Any other observations]
```

---

**Happy Testing! 🚀**

