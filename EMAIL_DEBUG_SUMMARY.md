# 📧 SMTP Email Debug Summary

## ✅ Test Results

### 1. SMTP Connection Test ✓
- **MAIL_SERVER**: smtp.gmail.com
- **MAIL_PORT**: 587
- **MAIL_USE_TLS**: True
- **MAIL_USE_SSL**: False
- **Status**: ✅ **Working correctly**
- **Test Result**: Successfully sent test email

### 2. Email Service Function Test ✓
- **Function**: `send_checkin_email()`
- **Status**: ✅ **Working correctly**
- **Test Result**: Successfully sent check-in confirmation email

### 3. Full Registration + Check-in Flow Test ✓
- **Registration**: ✅ Success
- **Check-in**: ✅ Success
- **Email Sent Flag**: ✅ True
- **Status**: ✅ **Complete flow working correctly**

## 🎯 Current Configuration

```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=hanhuyenxinchao@gmail.com
MAIL_PASSWORD= qhqx bmqv pshn jbzs
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_SENDER=hanhuyenxinchao@gmail.com
```

## 💡 If you're not receiving emails:

### ✓ First, verify these settings:
1. **Gmail app password** - Make sure you're using the 16-character app password
   - Go to: https://myaccount.google.com/
   - Click "Security" → "App passwords"
   - Select "Mail" and "Windows Computer"
   - Use the provided 16-character password
   
2. **Check your email inbox**:
   - Check **Spam/Junk** folder
   - Check **Promotions** tab (in Gmail)
   - Gmail might filter test emails

3. **Gmail security settings**:
   - Enable 2-Step Verification (required for app passwords)
   - Verify "Allow less secure app access" is enabled (if not using app passwords)

4. **Test your email address**:
   - The recipient email must be valid
   - Some email domains may block incoming test emails

### ✓ How to verify it's working:

**Option 1: Run the test script**
```bash
python test_smtp_debug.py
```
This sends a test email to the configured MAIL_USERNAME

**Option 2: Test full flow**
```bash
python test_full_flow_email.py
```
This simulates registration → check-in → email sending

**Option 3: Check app logs**
- Look for log file in `event_checkin/logs/` (if enabled)
- Should show: `✅ Email gửi thành công tới [email]`

## 🔧 Common Issues & Solutions

### Issue: "Authentication failed"
**Solution**:
- Use Gmail app password (16 characters)
- Enable 2-Step Verification in Gmail
- Update .env file with correct app password

### Issue: "Connection timeout"
**Solution**:
- Check internet connection
- Verify MAIL_PORT 587 is not blocked by firewall
- Try ping smtp.gmail.com

### Issue: "Email not received"
**Solution**:
- Check spam/junk folder
- Verify recipient email address is correct
- Wait a few minutes (may be delayed)
- Gmail might block mass-send attempts

### Issue: "TLS/SSL error"
**Solution**:
- Ensure MAIL_USE_TLS=true and MAIL_USE_SSL=false
- This is the correct Gmail SMTP configuration

## 📝 Test Results Log

Run these commands to test:

1. **Basic SMTP test**:
   ```bash
   .venv/Scripts/python.exe test_smtp_debug.py
   ```

2. **Email service test**:
   ```bash
   .venv/Scripts/python.exe test_email_service.py
   ```

3. **Full application flow**:
   ```bash
   .venv/Scripts/python.exe test_full_flow_email.py
   ```

## ✅ Conclusion

The SMTP email system is **fully functional**. If you're not receiving emails:

1. **First check**: Gmail spam/junk folder
2. **Second check**: Gmail account settings (app passwords, 2FA)
3. **Third check**: Recipient email addresses are valid
4. **Run tests** to confirm configuration is working

All tests confirm the email system is working correctly! 🎉
