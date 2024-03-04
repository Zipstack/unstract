ALTER ROLE unstract_dev SET client_encoding TO 'utf8';
ALTER ROLE unstract_dev SET default_transaction_isolation TO 'read committed';
ALTER ROLE unstract_dev SET timezone TO 'UTC';
ALTER USER unstract_dev CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE unstract_db TO unstract_dev;
CREATE DATABASE unstract;