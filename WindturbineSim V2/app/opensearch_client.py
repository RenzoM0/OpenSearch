import os
from opensearchpy import OpenSearch


def make_client() -> OpenSearch:
    host = os.getenv("OPENSEARCH_HOST", "https://localhost:9200")
    user = os.getenv("OPENSEARCH_USER", "admin")
    password = os.getenv("OPENSEARCH_PASS", "admin")
    verify = os.getenv("OPENSEARCH_VERIFY_CERTS", "false").lower() == "true"

    # opensearch-py verwacht hosts in dict form
    return OpenSearch(
        hosts=[host],
        http_auth=(user, password),
        use_ssl=host.startswith("https://"),
        verify_certs=verify,
        ssl_show_warn=False,
        timeout=30,
        max_retries=3,
        retry_on_timeout=True,
    )
