# List of allowed database modules that can be dynamically imported
ALLOWED_MODULES = {
    "mysql": "unstract.connectors.databases.mysql",
    "postgres": "unstract.connectors.databases.postgres",
    "mongodb": "unstract.connectors.databases.mongodb",
    "oracle": "unstract.connectors.databases.oracle",
    "sqlserver": "unstract.connectors.databases.sqlserver",
    # Add other allowed database modules here
}
