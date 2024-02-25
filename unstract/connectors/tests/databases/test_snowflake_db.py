import unittest

from unstract.connectors.databases.snowflake.snowflake import SnowflakeDB


class TestSnowflakeDB(unittest.TestCase):
    def test_something(self):
        sf = SnowflakeDB(
            {
                "user": "arun",
                "password": "PASSWORD",
                "account": "JX91721.ap-south-1",
                "database": "RESUME_COLLECTION",
                "schema": "PUBLIC",
                "warehouse": "COMPUTE_WH",
                "role": "",
            }
        )
        # engine = sf.get_engine()
        # try:
        #     with engine.connect() as connection:
        #         md = sqlalchemy.MetaData()
        #         table = sqlalchemy.Table(
        #               'RESUME', md, autoload=True, autoload_with=engine)
        #         columns = table.c
        #         for c in columns:
        #             print(c.name, c.type)
        #         # connection.execute("select current_version()")
        # except Exception as e:
        #     print(e)
        #
        # engine.dispose()

        cursor = sf.get_engine().cursor()
        results = cursor.execute("describe table RESUME")
        for c in results:
            print(c)

        self.assertIsNotNone(results)  # add assertion here


if __name__ == "__main__":
    unittest.main()
