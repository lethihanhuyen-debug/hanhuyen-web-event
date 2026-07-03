CREATE DATABASE IF NOT EXISTS checkin_event
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE checkin_event;

CREATE TABLE IF NOT EXISTS admins (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(50) NOT NULL COMMENT 'super_admin | admin',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by INT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NULL,
  CONSTRAINT fk_admins_created_by
    FOREIGN KEY (created_by) REFERENCES admins(id)
    ON UPDATE CASCADE
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS don_vi (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ten_don_vi VARCHAR(255) NOT NULL UNIQUE COMMENT 'VD: Cong nghe thong tin, Toan, Su, ...',
  is_active BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
  ma_cbsv VARCHAR(50) PRIMARY KEY,
  ho_ten VARCHAR(255) NOT NULL,
  don_vi_id INT NULL,
  chuc_vu VARCHAR(100),
  so_dien_thoai VARCHAR(20),
  email VARCHAR(255),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NULL,
  CONSTRAINT fk_users_don_vi
    FOREIGN KEY (don_vi_id) REFERENCES don_vi(id)
    ON UPDATE CASCADE
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ten_su_kien VARCHAR(255) NOT NULL,
  hinh VARCHAR(255),
  mo_ta TEXT,
  dia_diem VARCHAR(255),
  ngay_bat_dau DATETIME NOT NULL,
  ngay_ket_thuc DATETIME NOT NULL,
  thang INT NOT NULL,
  nam INT NOT NULL,
  thoi_gian_mo_dang_ky DATETIME NOT NULL,
  thoi_gian_dong_dang_ky DATETIME NOT NULL,
  trang_thai VARCHAR(50) NOT NULL DEFAULT 'upcoming' COMMENT 'upcoming | ongoing | closed',
  certificate_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  certificate_template VARCHAR(255),
  certificate_layout TEXT,
  created_by INT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_by INT NULL,
  updated_at DATETIME NULL,
  CONSTRAINT fk_events_created_by
    FOREIGN KEY (created_by) REFERENCES admins(id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  CONSTRAINT fk_events_updated_by
    FOREIGN KEY (updated_by) REFERENCES admins(id)
    ON UPDATE CASCADE
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS registrations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ma_cbsv VARCHAR(50) NOT NULL,
  event_id INT NOT NULL,
  thoi_gian_dang_ky DATETIME NOT NULL,
  UNIQUE KEY uq_registrations_user_event (ma_cbsv, event_id),
  CONSTRAINT fk_registrations_user
    FOREIGN KEY (ma_cbsv) REFERENCES users(ma_cbsv)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  CONSTRAINT fk_registrations_event
    FOREIGN KEY (event_id) REFERENCES events(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS checkins (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ma_cbsv VARCHAR(50) NOT NULL,
  event_id INT NOT NULL,
  thoi_gian_checkin DATETIME NOT NULL,
  UNIQUE KEY uq_checkins_user_event (ma_cbsv, event_id),
  CONSTRAINT fk_checkins_user
    FOREIGN KEY (ma_cbsv) REFERENCES users(ma_cbsv)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  CONSTRAINT fk_checkins_event
    FOREIGN KEY (event_id) REFERENCES events(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS certificates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ma_cbsv VARCHAR(50) NOT NULL,
  event_id INT NOT NULL,
  certificate_code VARCHAR(100) NOT NULL UNIQUE,
  file_url VARCHAR(255),
  file_type VARCHAR(20) NOT NULL DEFAULT 'png',
  status VARCHAR(50) NOT NULL DEFAULT 'generated',
  issued_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uq_certificates_user_event (ma_cbsv, event_id),
  KEY ix_certificates_certificate_code (certificate_code),
  CONSTRAINT fk_certificates_user
    FOREIGN KEY (ma_cbsv) REFERENCES users(ma_cbsv)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  CONSTRAINT fk_certificates_event
    FOREIGN KEY (event_id) REFERENCES events(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS email_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ma_cbsv VARCHAR(50) NOT NULL,
  event_id INT NOT NULL,
  email_to VARCHAR(255) NOT NULL,
  email_type VARCHAR(50) NOT NULL DEFAULT 'checkin_certificate',
  subject VARCHAR(255) NOT NULL,
  certificate_code VARCHAR(100) NULL,
  attachment_path VARCHAR(255) NULL,
  trang_thai VARCHAR(20) NOT NULL COMMENT 'success | failed',
  error_message TEXT NULL,
  sent_at DATETIME NOT NULL,
  KEY ix_email_logs_user_event (ma_cbsv, event_id),
  CONSTRAINT fk_email_logs_user
    FOREIGN KEY (ma_cbsv) REFERENCES users(ma_cbsv)
    ON UPDATE CASCADE
    ON DELETE RESTRICT,
  CONSTRAINT fk_email_logs_event
    FOREIGN KEY (event_id) REFERENCES events(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  CONSTRAINT fk_email_logs_certificate
    FOREIGN KEY (certificate_code) REFERENCES certificates(certificate_code)
    ON UPDATE CASCADE
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
