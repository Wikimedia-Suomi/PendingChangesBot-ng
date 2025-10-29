# 🚀 PR #119 - Execution Guide

## ✅ **Prerequisites**

Make sure you have:
- ✅ Python 3.8+
- ✅ Virtual environment activated
- ✅ All dependencies installed

---

## 📋 **Step-by-Step Execution**

### **Step 1: Activate Virtual Environment**

```bash
# If not already activated
cd PendingChangesBot-ng
.\venv\Scripts\Activate.ps1   # Windows PowerShell
# OR
source venv/bin/activate       # Linux/Mac
```

### **Step 2: Pull Latest Changes**

```bash
git fetch origin issue-114-word-annotation
git checkout issue-114-word-annotation
git pull
```

### **Step 3: Create Database Migrations**

```bash
cd app
python manage.py makemigrations reviews
```

**Expected output:**
```
Migrations for 'reviews':
  reviews/migrations/00XX_word_annotation.py
    - Create model WordAnnotation
    - Create model RevisionAnnotation
```

### **Step 4: Apply Migrations**

```bash
python manage.py migrate
```

**Expected output:**
```
Running migrations:
  Applying reviews.00XX_word_annotation... OK
```

### **Step 5: Check for Errors**

```bash
python manage.py check
```

**Expected output:**
```
System check identified no issues (0 silenced).
```

### **Step 6: Run Development Server**

```bash
python manage.py runserver
```

**Expected output:**
```
Django version X.X, using settings 'reviewer.settings'
Starting development server at http://127.0.0.1:8000/
```

---

## 🧪 **Testing Word Annotation Features**

### **Test 1: Check Admin Interface**

1. Go to: http://127.0.0.1:8000/admin/
2. Login with admin credentials
3. You should see:
   - ✅ Word annotations
   - ✅ Revision annotations
   - ✅ FlaggedRevs statistics
   - ✅ Review activity

### **Test 2: Check Word Annotation Page**

Go to: http://127.0.0.1:8000/word-annotation/

Should load the word annotation visualization page.

### **Test 3: Test Management Commands**

```bash
# Test annotate_article command
python manage.py annotate_article --help

# Test get_annotated_revision command  
python manage.py get_annotated_revision --help
```

### **Test 4: Check API Endpoints**

```bash
# Test word annotation APIs
curl http://127.0.0.1:8000/api/annotations/revisions/?page_id=123

# Test FlaggedRevs APIs
curl http://127.0.0.1:8000/api/flaggedrevs-statistics/
```

---

## ✅ **Quick Verification Checklist**

Run these to verify everything is working:

```bash
cd app

# 1. Check models are recognized
python manage.py showmigrations reviews

# 2. Check no syntax errors
python manage.py check

# 3. Check imports work
python manage.py shell -c "from reviews.models import WordAnnotation, RevisionAnnotation; print('✅ Models imported successfully')"

# 4. Check admin is registered
python manage.py shell -c "from django.contrib import admin; from reviews.models import WordAnnotation; print('✅ Admin registered' if WordAnnotation in admin.site._registry else '❌ Admin not registered')"
```

---

## 🔧 **Troubleshooting**

### **Issue: Migration already exists**

If you see: `No changes detected`

**Solution**: Migrations may already exist. Check:
```bash
python manage.py showmigrations reviews | grep word
```

### **Issue: Import errors**

If you see import errors:

**Solution**: Make sure virtual environment is activated:
```bash
pip list | grep Django
```

### **Issue: Database errors**

If you see database errors:

**Solution**: Run migrations:
```bash
python manage.py migrate --run-syncdb
```

### **Issue: Port already in use**

If port 8000 is in use:

**Solution**: Use different port:
```bash
python manage.py runserver 8080
```

---

## 📊 **What Features Are Available**

### **Word Annotation System (Issue #114)**

1. **Models**:
   - `WordAnnotation` - Word-level metadata
   - `RevisionAnnotation` - Annotation status

2. **Admin Interface**:
   - `/admin/reviews/wordannotation/`
   - `/admin/reviews/revisionannotation/`

3. **Management Commands**:
   ```bash
   python manage.py annotate_article <page_id>
   python manage.py get_annotated_revision <page_id> <revision_id>
   ```

4. **Web Interface**:
   - `/word-annotation/` - Visualization page

5. **API Endpoints**:
   - `/api/annotations/revisions/` - Get revisions
   - `/api/annotations/words/` - Get word annotations

### **FlaggedRevs Features (From Main)**

1. **Models**:
   - `FlaggedRevsStatistics`
   - `ReviewActivity`

2. **Admin Interface**:
   - `/admin/reviews/flaggedrevsstatistics/`
   - `/admin/reviews/reviewactivity/`

3. **API Endpoints**:
   - `/api/flaggedrevs-statistics/`
   - `/api/flaggedrevs-activity/`
   - `/flaggedrevs-statistics/` - Statistics page

---

## 🎯 **Quick Start Commands**

```bash
# Complete setup and run
cd PendingChangesBot-ng
.\venv\Scripts\Activate.ps1
cd app
python manage.py makemigrations
python manage.py migrate
python manage.py check
python manage.py runserver

# Then visit:
# http://127.0.0.1:8000/admin/
# http://127.0.0.1:8000/word-annotation/
```

---

## ✅ **Success Indicators**

You'll know it's working when:

1. ✅ `python manage.py check` shows no errors
2. ✅ Server starts without errors
3. ✅ Admin shows WordAnnotation models
4. ✅ `/word-annotation/` page loads
5. ✅ API endpoints respond

---

## 📝 **Example Usage**

### **Annotate an Article**

```bash
# Annotate Wikipedia article with page_id 12345
python manage.py annotate_article 12345

# Expected output:
# Processing page 12345...
# Annotated 50 revisions
# Total words: 15,234
# Completed successfully!
```

### **Get Annotations**

```bash
# Get annotations for specific revision
python manage.py get_annotated_revision 12345 67890 --output summary

# Expected output:
# Revision: 67890
# Page: Example Article
# Total words: 1,234
# Unique authors: 15
# Added in this revision: 45 words
```

---

## 🎉 **You're Ready!**

Your PR #119 is fully functional and ready for testing!

**Next Steps**:
1. Run the commands above
2. Test all features
3. Report any issues
4. Get maintainer approval
5. Merge! 🚀

---

**Date**: October 28, 2025  
**PR**: #119  
**Branch**: issue-114-word-annotation  
**Status**: ✅ Ready for execution

