import unittest

from unstract.connectors.databases.bigquery.bigquery import BigQuery


class TestBigQuery(unittest.TestCase):
    def test_json_credentials(self):
        bigquery = BigQuery(
            {
                "json_credentials": (
                    '{"type":"service_account","project_id":'
                    '"project_id","private_key_id":"private_key_id",'
                    '"private_key":"private_key","client_email":'
                    '"client_email","client_id":"11427061",'
                    '"auth_uri":"",'
                    '"token_uri":"",'
                    '"auth_provider_x509_cert_url":"",'
                    '"client_x509_cert_url":"",'
                    '"universe_domain":"googleapis.com"}'
                )
            }
        )
        client = bigquery.get_engine()
        query_job = client.query(
            """
        select * from `dataset.test`"""
        )
        results = query_job.result()

        for c in results:
            print(c)
        self.assertTrue(len(results) > 0)  # add assertion here


if __name__ == "__main__":
    unittest.main()
