# 🚀 Testing Guide: CAPTCHA OCR Automation

## What Changed

✅ **Frame Detachment** - Now automatically refreshes frame list on each loop iteration  
✅ **OCR Support** - Tesseract can automatically read CAPTCHA images  
✅ **Frontend Button** - New 🤖 OCR button to trigger auto-solve  
✅ **Better Error Messages** - Clearer diagnostics for debugging  

---

## 🧪 Test Scenarios

### Scenario 1: Manual CAPTCHA Entry (Current Working Method)

```
1. Start server: .venv/bin/python backend/app.py
2. Open: http://127.0.0.1:5000
3. Enter: Roll No, Password, Semester
4. Click: "Connect to Portal"
5. See: CAPTCHA image displayed
6. Manually read CAPTCHA and type in the input field
7. Click: "Verify & Deep Scrape"
8. Expected: ✓ Login succeeds, attendance data displayed
```

**Expected Time:** 25-55 seconds (including CAPTCHA solve time)

---

### Scenario 2: OCR Auto-Fill (NEW FEATURE)

```
1. Start server: .venv/bin/python backend/app.py
2. Open: http://127.0.0.1:5000
3. Enter: Roll No, Password, Semester
4. Click: "Connect to Portal"
5. See: CAPTCHA image + 🤖 OCR button
6. Click: 🤖 OCR button
7. Expected: "Reading..." → Auto-solves CAPTCHA → Login succeeds
```

**Expected Time:** 15-35 seconds (no manual CAPTCHA entry!)

**If OCR fails:** Fallback message suggests manual entry

---

### Scenario 3: Cache Hit (Instant Access)

```
1. After Scenario 1 or 2 completes:
2. Refresh browser or close/reopen
3. You'll see: "Verifying local cache..."
4. Expected: Chat window opens directly
5. No login/CAPTCHA needed!
```

**Expected Time:** 2-3 seconds

---

## 🔍 How to Debug

### Check If Tesseract Works

```bash
cd /Volumes/algsoch/sachin/Kairon/backend
../.venv/bin/python test_captcha_ocr.py
```

**Output will show:** How well Tesseract reads CAPTCHA images

### Enable Debug Logging

Check the server terminal for:
- `[INFO] ✓ POST /api/login` = Login frame found ✓
- `[DEBUG] Detected CAPTCHA via OCR: 'ABC123'` = OCR worked
- `[WARNING] ⚠ POST /api/captcha | Status: 401` = Login failed

### Save Debug Screenshots

If something fails, look for:
- `debug_attendance_link.png` - Portal structure after login
- `debug_captcha_ocr_error.png` - CAPTCHA image that failed OCR

---

## 🐛 Troubleshooting

| Problem | Solution |
|:---|:---|
| **"Could not find 'My Attendance' link"** | Portal HTML structure changed; check `debug_attendance_link.png` |
| **OCR shows "Frame was detached"** | Frame refresh logic triggered; retry should work |
| **"Frame was detached" error persists** | Portal navigation is very slow; increase wait times in scraper.py |
| **OCR accuracy very low** | NSUT's CAPTCHA is distorted; consider manual entry or API service |
| **Session expires too fast** | Check 5-minute TTL in app.py if needed |

---

## 📊 OCR Accuracy Testing

After running `test_captcha_ocr.py`, you'll see results like:

```
📋 OCR Results for captcha_1.png:
  Raw OCR:      'ABC123 extra noise'
  Cleaned:      'ABC123extraNoise'
  Enhanced:     'ABC123'
  Cleaned Enh:  'ABC123'
  
  ✓ Success rate: 75% (3/4 attempts)
```

**Interpretation:**
- ✓ >70% = Good, should use OCR
- ⚠ 40-70% = Fair, might need retries
- ✗ <40% = Poor, stick with manual entry

---

## 🎯 Success Criteria

Test is **PASSING** if:

✅ Manual CAPTCHA: User enters text, login works, data displays  
✅ OCR Auto-Fill: 🤖 button triggers, CAPTCHA auto-solved, login succeeds  
✅ Cache Hit: Second login instant without CAPTCHA  
✅ Error Handling: Frame errors handled gracefully with clear messages  

Test is **FAILING** if:

❌ "Frame was detached" appears repeatedly without recovery  
❌ "My Attendance" link never found even after retries  
❌ OCR accuracy <20% (unusable)  
❌ Session expires before scraping completes  

---

## 🚀 Next Steps After Testing

1. **If OCR works well (>70% accuracy):**
   - Consider making OCR default (remove manual entry option)
   - Disable OCR button, just call it automatically
   - Users don't see CAPTCHA at all!

2. **If OCR accuracy is low:**
   - Consider external OCR API (Google Cloud Vision, Azure Computer Vision)
   - May have better CAPTCHA detection
   - Trade-off: Costs money, but near-perfect accuracy

3. **If frame detachment still occurs:**
   - NSUT portal may have very complex navigation
   - Increase timeouts in scraper.py
   - Add more debug screenshots for analysis

---

## 📝 Commands to Run

### Start Server
```bash
cd /Volumes/algsoch/sachin/Kairon
.venv/bin/python backend/app.py
```

### Test OCR
```bash
cd /Volumes/algsoch/sachin/Kairon/backend
../.venv/bin/python test_captcha_ocr.py
```

### Check Logs (Real-time)
```bash
# In separate terminal, tail the server output:
tail -f server.log  # if you redirect output to file
```

### Reset Cache (Start Fresh)
```bash
rm -rf backend/data/*.json
```

---

## 📸 Screenshots to Check

After testing, these debug files may be generated:

| File | When Created | Shows |
|:---|:---|:---|
| `debug_attendance_link.png` | Frame finding fails | Portal structure after login |
| `debug_captcha_ocr_error.png` | OCR fails | CAPTCHA image that was unreadable |
| Server logs | Every request | Timing and status codes |

---

## ✨ Expected User Experience (After All Tests Pass)

```
1. Open http://127.0.0.1:5000
2. Enter roll no + password + semester
3. Click "Connect"
4. Wait ~2 seconds (for CAPTCHA load)
5. Click 🤖 OCR (or wait for auto-solve)
6. Chat interface opens automatically ✓
7. Start asking questions!
```

**Total time:** ~15-30 seconds (completely hands-free CAPTCHA)

---

## 💡 Pro Tips

- **Save bandwidth:** Use cache checks after first login
- **Bulk scraping:** Could loop through multiple roll numbers
- **Notification alerts:** Add SMS/email when attendance drops below threshold
- **Historical tracking:** Store attendance history for trend analysis
- **Export reports:** Generate PDF reports of attendance trends

---

## Questions or Issues?

1. Check `system.md` for architecture details
2. Check `ARCHITECTURE.md` for system design
3. Check `README.md` for API reference
4. Look at server logs for precise error messages
5. Run `test_captcha_ocr.py` to verify OCR capability
