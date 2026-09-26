-- Run once in the MariaDB console as a user allowed to create databases and grant privileges.
-- The test user must already exist. This script does not store a password.
-- This script does not modify the application database.
-- The test runner requires this database to be empty before each test.

CREATE DATABASE IF NOT EXISTS `warehouse_app_test`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON `warehouse_app_test`.*
    TO 'warehouse_app_test_user'@'%';

SHOW GRANTS FOR 'warehouse_app_test_user'@'%';
