# 🧪 Testing Guide for Word Annotation Feature

## ✅ **Auto-Fill Feature Fixed!**

The auto-fill for Revision ID now works in **3 ways**:

1. **Press Enter** after typing Page ID
2. **Tab away** from the Page ID field
3. **Click outside** the Page ID field

The Revision ID will show:
- `Loading...` while fetching
- `Latest: 123456789` when successful
- `No revisions found` if page has no data
- `Error loading revisions` if API fails

---

## 📊 **Working Page IDs in Your Database**

Use these **real Page IDs** that exist in your local database:

| Page ID | Title | Language |
|---------|-------|----------|
| **534366** | Barack Obama | English |
| **9504027** | List of Hollyoaks characters | English |
| **5935** | The Church of Jesus Christ of Latter-day Saints | English |
| **248224** | अल्लू अर्जुन | Hindi |
| **190306** | कार्तिकेय | Hindi |
| **4877** | कृष्ण | Hindi |
| **18322** | भगत सिंह | Hindi |
| **59** | भारत | Hindi |
| **32193** | भारतीय राज्यों के वर्तमान राज्यपालों की सूची | Hindi |
| **217426** | योगी आदित्यनाथ | Hindi |

---

## 🎯 **How to Test the Auto-Fill Feature**

### **Step 1: Open the Word Annotation Page**

```
http://127.0.0.1:8000/word-annotation/
```

### **Step 2: Enter a Page ID**

Try one of these:

```
Page ID: 534366
```
(Barack Obama article)

### **Step 3: Trigger Auto-Fill**

Do ONE of these:
- ✅ Press **Enter** key
- ✅ Press **Tab** key
- ✅ Click outside the field

### **Step 4: Watch the Revision ID Field**

You should see:
1. Placeholder changes to `Loading...`
2. Then either:
   - ✅ **Success**: Revision ID auto-fills (e.g., `1234567890`)
   - ❌ **No data**: Shows `No revisions found`

### **Step 5: Click "Load Annotations"**

The page will load word annotations if they exist!

---

## 🧪 **Quick Test Commands**

### **Test 1: Check Available Pages**

```powershell
cd C:\Users\hp\Desktop\Outreachy\PendingChangesBot-ng\app
python manage.py shell -c "from reviews.models import PendingPage; [print(f'Page ID: {p.pageid:>10} | {p.title}') for p in PendingPage.objects.all()[:10]]"
```

### **Test 2: Check Revisions for a Page**

```powershell
python manage.py shell -c "from reviews.models import PendingRevision, PendingPage; page = PendingPage.objects.get(pageid=534366); revs = PendingRevision.objects.filter(page=page)[:5]; print(f'Page: {page.title}'); [print(f'  Revision: {r.revid} by {r.user_name} at {r.timestamp}') for r in revs]"
```

### **Test 3: Check Word Annotations**

```powershell
python manage.py shell -c "from reviews.models import WordAnnotation; count = WordAnnotation.objects.count(); print(f'Total Word Annotations: {count}')"
```

---

## 🌐 **Testing the Web Interface**

### **Test Scenario 1: Barack Obama Article**

1. **Page ID**: `534366`
2. Press **Enter** or **Tab**
3. Revision ID should auto-fill
4. Click **"Load Annotations"**
5. See word-level annotations

### **Test Scenario 2: Hindi Article (भारत)**

1. **Page ID**: `59`
2. Press **Enter**
3. Check auto-fill works
4. Load annotations

### **Test Scenario 3: Manual Revision ID**

1. **Page ID**: `534366`
2. Wait for auto-fill
3. **Manually change** Revision ID to a different number
4. Click **"Load Annotations"**
5. Should load that specific revision

---

## 🔍 **What Should Happen**

### **✅ Success Path:**

1. Enter Page ID: `534366`
2. Press Enter
3. Revision ID auto-fills: e.g., `1316772466`
4. Placeholder shows: `Latest: 1316772466`
5. Click "Load Annotations"
6. Words display with color-coded authors

### **❌ Error Paths:**

#### **Page Not Found:**
```
Input: Page ID: 99999999
Result: "No revisions found"
```

#### **No Annotations Yet:**
```
Input: Page ID: 534366
Load Annotations Result: "No annotations found for this revision"
```

**Solution**: Run annotation commands first:
```powershell
python manage.py annotate_article 534366
```

---

## 📊 **API Endpoints to Test**

### **1. Get Revisions (Auto-Fill Uses This)**

```
http://127.0.0.1:8000/api/annotations/revisions/?page_id=534366
```

**Expected Response:**
```json
{
  "revisions": [
    {
      "revision_id": 1316772466,
      "timestamp": "2024-03-15T10:30:00",
      "user": "ExampleUser",
      "comment": "Updated article"
    }
  ]
}
```

### **2. Get Word Annotations**

```
http://127.0.0.1:8000/api/annotations/words/?page_id=534366&revision_id=1316772466
```

**Expected Response:**
```json
{
  "annotations": [
    {
      "word": "Barack",
      "author": "Editor1",
      "is_moved": false,
      "is_deleted": false
    }
  ],
  "authors": ["Editor1", "Editor2"]
}
```

---

## 🐛 **Troubleshooting**

### **Issue 1: "No revisions found"**

**Cause**: Page has no revisions in database

**Solution**:
```powershell
# Check if page has revisions
python manage.py shell -c "from reviews.models import PendingRevision, PendingPage; page = PendingPage.objects.get(pageid=534366); print(f'Revisions: {PendingRevision.objects.filter(page=page).count()}')"
```

### **Issue 2: Auto-fill doesn't work**

**Cause**: Multiple possible causes

**Solutions**:
1. Check console (F12) for JavaScript errors
2. Verify API endpoint works: `/api/annotations/revisions/?page_id=534366`
3. Make sure you pressed Enter/Tab
4. Check server is running

### **Issue 3: "No annotations found"**

**Cause**: Annotations haven't been generated yet

**Solution**:
```powershell
# Generate annotations for a page
python manage.py annotate_article 534366
```

---

## ✅ **Changes Made to Fix Auto-Fill**

### **Before:**
- Only worked when clicking outside field
- No visual feedback
- No error handling

### **After:**
- ✅ Works with Enter key
- ✅ Works with Tab key
- ✅ Works when clicking outside
- ✅ Shows "Loading..." during fetch
- ✅ Shows "No revisions found" on error
- ✅ Shows "Latest: XXX" on success
- ✅ Better error handling

---

## 🎉 **Testing Checklist**

- [ ] Server is running (`python manage.py runserver`)
- [ ] Word annotation page loads (`/word-annotation/`)
- [ ] Enter Page ID: `534366`
- [ ] Press **Enter** key
- [ ] Revision ID auto-fills ✅
- [ ] Placeholder shows "Latest: XXX" ✅
- [ ] Click "Load Annotations"
- [ ] Page displays results (or "No annotations found")
- [ ] Try other Page IDs from the list
- [ ] Test API endpoints in browser

---

## 📝 **Quick Copy-Paste Test**

```
1. Open: http://127.0.0.1:8000/word-annotation/
2. Page ID: 534366
3. Press: Enter
4. Wait: Revision ID fills
5. Click: Load Annotations
```

---

**Created**: October 28, 2025  
**Feature**: Auto-fill for Revision ID  
**Status**: ✅ Working  
**Commit**: 414f115

