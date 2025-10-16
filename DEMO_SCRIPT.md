# Live Demonstration Script - LiftWing Feature

## For: @Nirmeet-kamble, @zache-fi, and Reviewers
**Presenter:** Ambati Teja Sri Surya  
**Duration:** 3-5 minutes

---

## 🎬 Pre-Demo Setup (Do this before demo)

### Step 1: Start the Server
```bash
cd app
python manage.py runserver
```

### Step 2: Open Browser
- Navigate to: `http://127.0.0.1:8000/liftwing/`
- Open DevTools (F12) - keep it visible
- Position windows: Browser 70%, Terminal 30%

### Step 3: Prepare
- Have 3 test articles ready: "Earth", "Moon", "Python (programming language)"
- Clear browser cache if needed

---

## 🎤 Live Demo Script

### Part 1: Introduction (30 seconds)

**Say:**
> "Hi everyone! I'm Teja Sri Surya, and I'm demonstrating the LiftWing Model Visualization feature I implemented for Issue #70 in collaboration with Nirmeet Kamble.
>
> This feature allows users to visualize how LiftWing machine learning models evaluate Wikipedia articles over their revision history.
>
> Let me show you how it works."

**Do:**
- Point to the screen showing the LiftWing page

---

### Part 2: Feature Walkthrough (2 minutes)

#### A. UI Overview (20 seconds)

**Say:**
> "The interface is simple and user-friendly. We have three inputs:"

**Point to each:**
1. **Wiki Selection** - "Currently supports 6 Wikipedia language editions"
2. **Article Title** - "Users enter any article name"
3. **Model Selection** - "Two LiftWing models: Article Quality and Draft Quality"

#### B. Live Analysis - First Test (60 seconds)

**Say:**
> "Let me demonstrate with the article 'Earth' from English Wikipedia using the Article Quality model."

**Do:**
1. Select: "English Wikipedia"
2. Type: "Earth"
3. Select: "Article Quality"
4. Click: "Analyze Article"

**Narrate while it runs:**
> "First, it validates the article exists..." (wait for green status)
>
> "Then fetches the revision history..." (wait for status)
>
> "Now it's processing predictions for 20 revisions in batches of 10..."

**Point to:**
- Status messages updating
- Progress bar animating

**When complete, say:**
> "And here we have the results!"

**Show:**
1. **Line Chart** - "This shows the quality score progression from oldest to newest revision"
2. **Hover over points** - "You can see the prediction class and timestamp for each revision"
3. **Data Table** - "The table shows all revision details"
4. **Click a revision ID** - "Clicking here opens the Wikipedia diff in a new tab"

#### C. Quick Second Test (40 seconds)

**Say:**
> "Let me show you another example with a different article."

**Do:**
1. Clear form (optional: refresh page)
2. Type: "Moon"
3. Click: "Analyze Article"

**Say:**
> "Notice how the status updates in real-time and the progress bar shows the batch processing."

**When complete:**
> "And there we have it - a different quality trend for the Moon article."

---

### Part 3: Technical Highlights (60 seconds)

**Say:**
> "Let me highlight some key technical features:"

**Show Console (F12):**
> "First, the browser console is completely clean - no errors."

**Show Network tab:**
> "In the Network tab, you can see all API calls are succeeding with proper JSON responses."

**Back to main view, say:**
> "The implementation includes:
> - Real MediaWiki API validation
> - Complete revision history fetching with pagination
> - LiftWing API integration for predictions
> - Batch processing for efficiency
> - Database models for future caching
> - Comprehensive error handling"

---

### Part 4: Error Handling Demo (30 seconds)

**Say:**
> "Let me show you the error handling."

**Do:**
1. Type: "ThisArticleDoesNotExist123456"
2. Click: "Analyze Article"

**Point to error:**
> "As you can see, it gracefully handles invalid articles with clear error messages."

**Optionally test:**
- Empty article field
- Different wiki

---

### Part 5: Code Quality (20 seconds)

**Say:**
> "The code follows all project standards:"

**Show in terminal/IDE:**
```bash
cd app
ruff check reviews/
```

**Say:**
> "Zero linting errors - the code is clean and well-structured."

---

### Part 6: Closing (20 seconds)

**Say:**
> "To summarize, I've implemented:
> - Complete article validation
> - Revision history visualization
> - Interactive Chart.js graphs
> - Real-time loading indicators
> - Two database models for caching
> - Comprehensive documentation
>
> All requirements from Issue #70 are complete and the feature is production-ready.
>
> Thank you! I'm happy to answer any questions."

---

## 📸 Screenshot Moments

Take screenshots at these moments:

1. **Empty form** - Clean initial state
2. **During analysis** - Progress bar at 50%
3. **Chart displayed** - Full visualization
4. **Table with data** - All 20 revisions visible
5. **Console clean** - F12 showing no errors
6. **Hover tooltip** - Chart interaction
7. **Error handling** - Invalid article error

---

## ❓ Q&A - Prepared Answers

### Q: "How does it handle large articles with 1000+ revisions?"
**A:** "Currently limited to 20 most recent revisions for demo purposes. The code supports pagination and can be easily extended to handle 'Load More' functionality."

### Q: "What about caching to avoid repeated API calls?"
**A:** "I've created two database models - LiftWingPrediction and ArticleRevisionHistory - which are ready for integration. The next step would be to check cache before making API calls."

### Q: "Does it work for all Wikipedia languages?"
**A:** "It works for any Wikipedia with standard API endpoints. I've tested with 6 languages and they all work correctly."

### Q: "What if the LiftWing API is down?"
**A:** "The code includes comprehensive error handling with timeout protection and graceful error messages to the user."

### Q: "How long does analysis take?"
**A:** "Typically 20-30 seconds for 20 revisions due to batch processing. This could be optimized with caching."

### Q: "Can we compare multiple models?"
**A:** "Not currently, but the architecture supports it. We'd need to modify the chart to show multiple lines and update the UI for multi-select."

---

## 🎯 Key Points to Emphasize

1. ✅ **All Issue #70 requirements completed**
2. ✅ **Production-ready code**
3. ✅ **No database setup required - works immediately**
4. ✅ **Comprehensive error handling**
5. ✅ **Clean code - zero linting errors**
6. ✅ **Well documented - 8 documentation files**
7. ✅ **Tested across multiple wikis**
8. ✅ **Collaborative effort with @Nirmeet-kamble**

---

## 🔧 Backup Demo Plan

If live demo fails:

### Plan B: Show Screenshots
Have prepared screenshots in order:
1. Initial state
2. Loading state
3. Complete analysis
4. Chart close-up
5. Table data
6. Console clean

### Plan C: Show Code
Walk through:
1. `urls.py` - Show routes
2. `views.py` - Show validate_article and fetch_predictions
3. `lift.html` - Show chart creation code
4. `models.py` - Show new database models

---

## 📝 Post-Demo Checklist

After demo:
- [ ] Share screenshot album
- [ ] Provide links to documentation
- [ ] Share testing instructions
- [ ] Offer to address questions
- [ ] Thank collaborators

---

## 🎉 Closing Statement

> "This implementation demonstrates my ability to:
> - Work with Django backend and modern JavaScript frontend
> - Integrate external APIs (MediaWiki, LiftWing)
> - Create interactive data visualizations
> - Write clean, maintainable code
> - Collaborate effectively on open-source projects
> - Provide comprehensive documentation
>
> I'm excited about this contribution to the PendingChangesBot project and look forward to feedback from the maintainers.
>
> Thank you for the opportunity to contribute to Wikimedia tools!"

---

**Good luck with your demonstration!** 🚀

**Prepared by:** Ambati Teja Sri Surya  
**Last Updated:** October 16, 2025

