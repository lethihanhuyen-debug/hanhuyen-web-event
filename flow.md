# CERTIFICATE GENERATION SYSTEM PLAN

## Event Management & Digital Certificate Module

### Senior Developer Architecture Plan

---

# 1. Overview

## Objective

Build a scalable certificate generation module for the Event Management System.

When a student:

* registers for an event
* successfully attends/checks-in
* satisfies participation conditions

the system will automatically generate a digital certificate (PNG/PDF).

---

# 2. Current Existing Database

Current system already has:

* USERS
* EVENTS
* REGISTRATIONS
* CHECKINS
* ADMINS
* EMAIL_LOGS
* DON_VI

This is already enough foundation to build a production-ready certificate system.

---

# 3. Business Flow

```text
Student Register Event
        ↓
REGISTRATIONS
        ↓
Student Check-in Event
        ↓
CHECKINS
        ↓
System Validate Participation
        ↓
Generate Certificate
        ↓
Store Certificate Metadata
        ↓
Allow Download / Verification
```

---

# 4. Recommended Architecture

## Recommended Design

Use:

```text
Template-based Certificate Rendering
```

Instead of generating certificates manually.

---

# 5. Recommended Module Structure

```text
modules/
│
├── auth/
├── users/
├── events/
├── registrations/
├── checkins/
├── certificates/
│   ├── services/
│   ├── templates/
│   ├── generators/
│   ├── storage/
│   └── validators/
```

---

# 6. Database Design Upgrade

## 6.1 Add CERTIFICATES Table

```sql
CREATE TABLE CERTIFICATES (
    id INT PRIMARY KEY AUTO_INCREMENT,
    
    ma_cbsv VARCHAR(50) NOT NULL,
    event_id INT NOT NULL,

    certificate_code VARCHAR(100) UNIQUE NOT NULL,

    file_url VARCHAR(255),
    file_type VARCHAR(20),

    status VARCHAR(50) DEFAULT 'generated',

    issued_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,

    FOREIGN KEY (ma_cbsv) REFERENCES USERS(ma_cbsv),
    FOREIGN KEY (event_id) REFERENCES EVENTS(id)
);
```

---

## 6.2 Recommended EVENTS Upgrade

```sql
ALTER TABLE EVENTS
ADD COLUMN certificate_enabled BOOLEAN DEFAULT TRUE,
ADD COLUMN certificate_template VARCHAR(255),
ADD COLUMN certificate_title VARCHAR(255),
ADD COLUMN certificate_description TEXT;
```

---

# 7. Certificate Eligibility Rules

A student is eligible when:

```text
Registered Event
AND
Successfully Checked-in
```

SQL Logic:

```sql
SELECT *
FROM registrations r
JOIN checkins c
ON r.ma_cbsv = c.ma_cbsv
AND r.event_id = c.event_id
WHERE r.ma_cbsv = ?
AND r.event_id = ?;
```

If result exists → eligible.

---

# 8. Recommended Certificate Generation Strategy

## Preferred Solution (Production Friendly)

Use:

```text
Certificate Template Image + Dynamic Text Rendering
```

Recommended because:

* Easier to maintain
* Works with existing projects
* Technology-independent
* Faster implementation
* Exact visual output like real certificates
* Easy for admin to change templates later

---

# 9. Technology Recommendations

## Option A — NodeJS Existing Project

Recommended Libraries:

```text
canvas
sharp
pdf-lib
puppeteer
```

---

## Option B — Java Spring Boot

Recommended Libraries:

```text
Apache PDFBox
iTextPDF
Graphics2D
```

---

## Option C — Python Existing Project

Recommended Libraries:

```text
Pillow
ReportLab
FPDF
```

---

# 10. Final Recommended Approach

## Use Image Template Rendering

```text
certificate_template.png
        +
dynamic student data
        ↓
generated_certificate.png
        ↓
optional PDF export
```

This approach works with ANY backend stack.

---

# 11. Certificate Rendering Engine

## Responsibilities

Certificate Engine should:

```text
1. Validate participation
2. Load certificate template
3. Render dynamic texts
4. Export PNG/PDF
5. Upload storage
6. Save DB metadata
7. Return download URL
```

---

# 12. Suggested Folder Structure

```text
certificates/
│
├── templates/
│   ├── event_1.png
│   ├── event_2.png
│
├── generated/
│   ├── 2026/
│   ├── 2027/
│
├── fonts/
│
├── services/
│   ├── certificate.service.js
│
├── generators/
│   ├── image.generator.js
│   ├── pdf.generator.js
│
└── validators/
    ├── certificate.validator.js
```

---

# 13. Recommended API Design

## 13.1 Register Event

```http
POST /api/events/:eventId/register
```

---

## 13.2 Check-in Event

```http
POST /api/events/:eventId/checkin
```

---

## 13.3 Generate Certificate

```http
POST /api/certificates/generate
```

Payload:

```json
{
  "ma_cbsv": "2456090063",
  "event_id": 10
}
```

---

## 13.4 Download Certificate

```http
GET /api/certificates/:certificateCode
```

---

## 13.5 Student Certificate List

```http
GET /api/users/:ma_cbsv/certificates
```

---

# 14. Recommended Certificate Generation Flow

```text
API Request
    ↓
Validate Registration
    ↓
Validate Check-in
    ↓
Prevent Duplicate Certificate
    ↓
Load Student Data
    ↓
Load Event Data
    ↓
Generate Certificate Code
    ↓
Render Certificate
    ↓
Save Generated File
    ↓
Insert CERTIFICATES Record
    ↓
Return Download URL
```

---

# 15. Certificate Code Strategy

## Recommended Format

```text
USSH-2026-EVENT001-000001
```

Benefits:

* searchable
* verifiable
* prevents fake certificates
* easy admin tracking

---

# 16. Anti-Duplicate Logic

Before generating:

```sql
SELECT *
FROM CERTIFICATES
WHERE ma_cbsv = ?
AND event_id = ?;
```

If exists:

```text
Return existing certificate
```

Do NOT regenerate.

---

# 17. Certificate Verification Page

## Recommended Public Route

```http
GET /verify/:certificateCode
```

Page shows:

```text
Student Name
Student ID
Event Name
Issue Date
Certificate Status
```

---

# 18. Storage Recommendations

## Small Project

Use:

```text
Local Storage
```

Example:

```text
/public/certificates/
```

---

## Production System

Use:

```text
AWS S3
Cloudinary
MinIO
Google Cloud Storage
```

---

# 19. Email Integration (Recommended)

After certificate generation:

```text
Auto Send Email
```

Using existing:

```text
EMAIL_LOGS
```

Flow:

```text
Generate Certificate
    ↓
Send Email
    ↓
Log EMAIL_LOGS
```

---

# 20. Security Recommendations

## Must Implement

### Validate Download Permission

Students should only download:

```text
their own certificates
```

unless admin.

---

### Signed URLs (Production)

Use expiring download links.

---

### Watermark / QR Verification

Optional future upgrade.

---

# 21. Performance Recommendations

## Avoid Synchronous Rendering

Use:

```text
Queue Job / Background Worker
```

Example:

```text
BullMQ
RabbitMQ
Redis Queue
```

Especially when:

```text
500+ certificates generated
```

---

# 22. Recommended Admin Features

## Admin Dashboard

### Features

```text
- Upload certificate template
- Preview certificate
- Bulk generate certificates
- Export certificate list
- Revoke certificates
- Re-send email
```

---

# 23. Bulk Generation Strategy

## Recommended

```text
Generate certificates asynchronously
```

Flow:

```text
Admin Click Generate All
        ↓
Queue Students
        ↓
Worker Generates Files
        ↓
Store Results
```

---

# 24. Future Upgrade Possibilities

## Recommended Future Features

### QR Verification

QR contains:

```text
certificate verification URL
```

---

### Blockchain Verification

Optional enterprise-level upgrade.

---

### Multi-language Certificates

```text
Vietnamese
English
```

---

### Dynamic Signature

Admin signature overlay.

---

# 25. Recommended MVP Scope

## Phase 1 (Must Have)

```text
✔ Registration
✔ Check-in
✔ Certificate generation
✔ PNG/PDF export
✔ Download link
✔ Certificate DB storage
```

---

## Phase 2

```text
✔ Email sending
✔ QR verification
✔ Bulk generation
✔ Admin management
```

---

## Phase 3

```text
✔ Public verification portal
✔ Cloud storage
✔ Async workers
✔ Analytics dashboard
```

---

# 26. Senior Dev Recommendations

## DO NOT

```text
❌ Hardcode certificate text positions everywhere
❌ Generate duplicate certificates
❌ Store only files without DB records
❌ Render certificates synchronously for large events
❌ Depend heavily on one specific framework
```

---

## DO

```text
✔ Use reusable template engine
✔ Store metadata in DB
✔ Separate rendering logic
✔ Add verification mechanism
✔ Make system scalable
✔ Keep certificate generation isolated
```

---

# 27. Final Technical Recommendation

## Best Architecture For Current System

### Recommended Stack-Agnostic Solution

```text
Template Image Rendering Engine
+
Certificate Service Layer
+
Database Metadata Tracking
+
Download/Verification Module
```

This is:

```text
✔ scalable
✔ maintainable
✔ framework-independent
✔ production-friendly
✔ suitable for university systems
✔ suitable for enterprise event systems
```

---

# 28. Final Summary

## Core Flow

```text
Register
→ Check-in
→ Validate
→ Generate Certificate
→ Save Metadata
→ Download / Verify
```

---

# 29. Suggested Next Step

## Immediate Implementation Order

```text
1. Add CERTIFICATES table
2. Create Certificate Service
3. Create Template Renderer
4. Build Generate API
5. Build Download API
6. Build Verification Page
7. Add Email Sending
```

---

# 30. Recommended Deliverables

```text
✔ Certificate Generator Module
✔ Certificate Database
✔ Download System
✔ Verification System
✔ Admin Generation Dashboard
✔ Email Delivery
✔ PNG/PDF Export
```
