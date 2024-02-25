from .mariadb import MariaDB

metadata = {
    "name": MariaDB.__name__,
    "version": "1.0.0",
    "connector": MariaDB,
    "description": "MariaDB connector",
    "is_active": True,
}
