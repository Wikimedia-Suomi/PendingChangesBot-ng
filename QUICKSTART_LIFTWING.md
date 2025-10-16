# 🚀 Quick Start Guide - LiftWing Feature

## ⚡ Get Started in 3 Steps

### Step 1: Apply Database Migrations (30 seconds)

Open PowerShell/Terminal in the project directory:

```powershell
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
...
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, reviews, sessions
Running migrations:
  Applying reviews.0008_liftwingprediction_articlerevisionhistory... OK
```

---

### Step 2: Start the Server (5 seconds)

```powershell
python manage.py runserver
```

**Expected Output:**
```
Watching for file changes with StatReloader
Performing system checks...

System check identified no issues (0 silenced).
October 16, 2025 - 10:30:45
Django version 4.2.x, using settings 'reviewer.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

---

### Step 3: Test the Feature (1 minute)

1. **Open Browser:** Navigate to `http://127.0.0.1:8000/liftwing/`

2. **Fill in the form:**
   - **Wiki:** English Wikipedia
   - **Article:** `Python (programming language)`
   - **Model:** Article Quality

3. **Click:** 📊 Analyze Article

4. **Watch the magic happen:**
   - ✅ Article validation (2 seconds)
   - ✅ Fetching revisions (3 seconds)
   - ✅ Processing predictions (15-20 seconds)
   - ✅ Chart appears with quality trend
   - ✅ Table shows revision history

---

## 🎯 First-Time Test Recommendations

### Easy Tests (Fast & Reliable)

```
📝 Test 1: Simple Article
Wiki: English Wikipedia
Article: Earth
Model: Article Quality
⏱️ Time: ~20 seconds
```

```
📝 Test 2: Programming Article
Wiki: English Wikipedia
Article: JavaScript
Model: Article Quality
⏱️ Time: ~25 seconds
```

```
📝 Test 3: Different Wiki
Wiki: German Wikipedia
Article: Berlin
Model: Article Quality
⏱️ Time: ~20 seconds
```

### What to Look For

✅ **Success Indicators:**
- Green status messages appear
- Progress bar animates from 0% to 100%
- Line chart displays with colored line
- Table populates with ~20 rows
- Clicking revision IDs opens Wikipedia diffs

❌ **If Something Fails:**
- Red error message appears
- Check console (F12) for JavaScript errors
- Verify internet connection
- Try a different article

---

## 🎨 Feature Highlights

### What You'll See

#### 1. **Interactive Chart**
- **X-axis:** Revision sequence (Rev 1, Rev 2, ...)
- **Y-axis:** Quality score (1-6)
- **Hover:** Shows prediction class and timestamp
- **Responsive:** Resizes with browser window

#### 2. **Revision Table**
| Column | Description |
|--------|-------------|
| # | Sequence number |
| Revision ID | Clickable link to Wikipedia diff |
| Timestamp | When the edit was made |
| User | Who made the edit |
| Comment | Edit summary (truncated) |
| Prediction | Quality class (FA, GA, B, C, Start, Stub) |

#### 3. **Loading Experience**
- Status messages guide you through each step
- Progress bar shows batch processing
- Button state changes during loading
- Smooth animations and transitions

---

## 🐛 Troubleshooting

### Issue: "Article not found"
**Solution:** 
- Check spelling of article title
- Try another article (e.g., "Earth")
- Verify wiki selection matches article language

### Issue: Loading takes forever
**Solution:**
- First run is always slower (cold start)
- LiftWing API can be slow sometimes
- Normal time: 15-30 seconds for 20 revisions
- If >60 seconds, refresh and try again

### Issue: Chart doesn't appear
**Solution:**
1. Press F12 to open DevTools
2. Check Console for errors
3. Refresh the page
4. Try a different browser (Chrome recommended)

### Issue: Server won't start
**Solution:**
```powershell
# Make sure you're in the app directory
cd app

# Check if port 8000 is already in use
# Kill any existing Django processes

# Try running on different port
python manage.py runserver 8080
```

---

## 📸 What Success Looks Like

### Before Analysis
```
┌─────────────────────────────────────┐
│  🚀 LiftWing Model Visualization    │
├─────────────────────────────────────┤
│  Wiki: [English Wikipedia ▼]        │
│  Article: [____________]             │
│  Model: [Article Quality ▼]         │
│  [📊 Analyze Article]               │
└─────────────────────────────────────┘
```

### During Analysis
```
┌─────────────────────────────────────┐
│  Status: 🤖 Fetching predictions... │
│  [████████░░░░░░░░░░] 40%          │
│  [⏳ Analyzing...]                  │
└─────────────────────────────────────┘
```

### After Analysis
```
┌─────────────────────────────────────┐
│  ✅ Analysis complete! 20 revisions │
│                                     │
│  📈 Chart showing quality trend     │
│  📋 Table with all revisions        │
└─────────────────────────────────────┘
```

---

## 📊 Try These Test Cases

### Test Suite (5 minutes total)

1. **Valid Article:** `Earth` ✅
2. **Invalid Article:** `XYZ123NotReal` ❌
3. **Long Title:** `Python (programming language)` ✅
4. **Different Wiki:** `Berlin` (German) ✅
5. **Short Article:** `Moon` ✅

---

## 🎉 You're All Set!

The LiftWing visualization feature is now running on your machine.

### Next Steps

1. ✅ Test with different articles
2. ✅ Try multiple wikis
3. ✅ Explore the chart interactions
4. ✅ Click revision links in the table
5. 📝 Report any issues you find

### Need Help?

- **Documentation:** See `LIFTWING_FEATURE_GUIDE.md`
- **Testing:** See `TEST_LIFTWING.md`
- **Summary:** See `IMPLEMENTATION_SUMMARY.md`

---

## 📋 Commands Reference

```powershell
# Navigate to app directory
cd app

# Apply migrations
python manage.py makemigrations
python manage.py migrate

# Start server
python manage.py runserver

# Run on different port
python manage.py runserver 8080

# Create superuser (for Django admin)
python manage.py createsuperuser

# Access Django admin
# http://127.0.0.1:8000/admin/
```

---

**Happy Analyzing! 🚀**

**Feature Status:** ✅ Fully Functional  
**Last Updated:** October 16, 2025  
**Developed by:** Ambati Teja Sri Surya

