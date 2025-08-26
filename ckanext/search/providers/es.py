import hashlib
import json
import logging
from typing import Any, Optional

from ckan.plugins import SingletonPlugin, implements
from ckan.plugins.toolkit import config
from elasticsearch import Elasticsearch

from ckanext.search.interfaces import ISearchProvider, SearchResults, SearchSchema
from ckanext.search.filters import FilterOp

log = logging.getLogger(__name__)


class ElasticSearchProvider(SingletonPlugin):

    implements(ISearchProvider, inherit=True)

    id = "elasticsearch"

    _client = None

    _index_name = ""

    def __init__(self, *args: Any, **kwargs: Any):

        super().__init__(*args, **kwargs)

        # TODO: config declaration
        self._index_name = config.get("ckan.search.elasticsearch.index_name", "ckan")

    # ISearchProvider

    def initialize_search_provider(
        self, search_schema: SearchSchema, clear: bool
    ) -> None:

        client = self.get_client()

        # This will raise an exception if there are connection issues
        log.debug(client.info())

        # Check if index exists, create otherwise
        if not client.indices.exists(index=self._index_name):

            # TODO: what else do we need?
            params = {"index": self._index_name, "mappings": {"dynamic": "false"}}

            client.indices.create(**params)
            log.info("Created new index '%s'" % self._index_name)

        # Translate common search schema format to ES format
        es_field_types = {
            "string": "keyword",
            "bool": "boolean",
        }

        mapping = {"properties": {}}
        for field_name, field in search_schema.get("fields", {}).items():

            field_type = field.pop("type")

            if field_type in es_field_types:
                field_type = es_field_types[field_type]

            # All fields are multivalued by default
            mapping["properties"][field_name] = {
                "type": field_type,
                "index": field.get("indexed", True),
                "store": field.get("stored", False),
            }
            log.info(
                f"Added field '{field_name}' to index, with type {field_type} and params {field}"
            )

        client.indices.put_mapping(index=self._index_name, body=mapping)
        log.info("Updated index with mapping")

    def index_search_record(
        self,
        entity_type: str,
        id_: str,
        search_data: dict[str, str | list[str]],
        search_schema: SearchSchema,
    ) -> None:
        # TODO: provider specific params

        client = self.get_client()

        index_id = id_

        # TODO: choose what to commit
        search_data.pop("organization", None)
        # TODO: refresh
        client.index(
            index=self._index_name, id=index_id, document=search_data, refresh="true"
        )

    def search_query(
        self,
        q: str,
        filters: FilterOp,
        sort: list[list[str]],
        additional_params: dict[str, Any],
        lang: str,
        search_schema: SearchSchema,
        return_ids: bool = False,
        return_entity_types: bool = False,
        return_facets: bool = False,
        limit: int = 20,
        start: int = 0,
    ) -> Optional[SearchResults]:

        es_params = {"size": limit, "from": start}

        # Translate q param to ES Query DSL
        if q and q in ("*", "*:*"):
            q_dsl = {"match_all": {}}
        elif q:
            q_dsl = {"simple_query_string": {"query": q}}
        else:
            q_dsl = None

        # Transform generic search params to ES Query DSL
        filters_dsl = self._filterop_to_es_query(filters, search_schema)

        if q_dsl and filters_dsl:
            es_params["query"] = {"bool": {"must": [q_dsl, filters_dsl]}}
        elif q_dsl:
            es_params["query"] = q_dsl
        elif filters_dsl:
            es_params["query"] = filters_dsl
        else:
            es_params["query"] = {"match_all": {}}

        client = self.get_client()

        # TODO: error handling
        es_response = client.search(index=self._index_name, **es_params)

        items = []
        for doc in es_response["hits"]["hits"]:
            doc = doc["_source"]
            # TODO allow to choose validated/not validated? i.e use_default_schema
            items.append(json.loads(doc["validated_data_dict"]))

        return {
            "count": es_response["hits"]["total"]["value"],
            "results": items,
            "facets": {},
        }

    def _filterop_to_es_query(
        self, filter_op: FilterOp, search_schema: SearchSchema
    ) -> Optional[dict]:
        """
        Convert a FilterOp object to ElasticSearch DSL query.
        Returns a dict representing the ES query DSL.
        """
        if not filter_op:
            return None

        if not isinstance(filter_op, FilterOp):
            raise ValueError("A FilterOp object is needed")

        if filter_op.op in ["$and", "$or"]:
            if not isinstance(filter_op.value, list):
                return None

            sub_queries = []
            for sub_op in filter_op.value:
                if isinstance(sub_op, FilterOp):
                    sub_query = self._filterop_to_es_query(sub_op, search_schema)
                    if sub_query:
                        sub_queries.append(sub_query)

            if not sub_queries:
                return None

            if len(sub_queries) == 1:
                return sub_queries[0]

            if filter_op.op == "$and":
                return {"bool": {"must": sub_queries}}
            else:  # $or
                return {"bool": {"should": sub_queries, "minimum_should_match": 1}}

        else:
            # Handle field operators
            field_name = filter_op.field
            op = filter_op.op
            value = filter_op.value

            if not field_name:
                return None

            field_type = self._get_field_type(field_name, search_schema)

            if op == "eq":
                return {"term": {field_name: value}}
            elif op == "gt":
                return {"range": {field_name: {"gt": value}}}
            elif op == "gte":
                return {"range": {field_name: {"gte": value}}}
            elif op == "lt":
                return {"range": {field_name: {"lt": value}}}
            elif op == "lte":
                return {"range": {field_name: {"lte": value}}}
            elif op == "in":
                if isinstance(value, list) and value:
                    return {"terms": {field_name: value}}
                else:
                    return None
            else:
                # Unknown operator, assume equality for now
                return {"term": {field_name: value}}

    def _get_field_type(
        self, field_name: str, search_schema: SearchSchema
    ) -> Optional[str]:
        """Get field type from search schema."""
        if field_info := search_schema.get("fields", {}).get(field_name):
            return field_info.get("type")
        return None

    def clear_index(self) -> None:

        client = self.get_client()
        # TODO: review bulk, versions, slices, etc
        # TODO: wait for completion
        client.delete_by_query(
            index=self._index_name,
            body={"query": {"match_all": {}}},
            conflicts="proceed",
            wait_for_completion=True,
        )
        log.info("Cleared all documents in the search index")

    # Provider methods

    def get_client(self) -> Elasticsearch:

        if self._client:
            return self._client

        # TODO: config declaration
        es_config = {}
        if ca_certs_path := config.get("ckan.search.elasticsearch.ca_certs_path"):
            es_config["ca_certs"] = ca_certs_path

        if password := config.get("ckan.search.elasticsearch.password"):
            es_config["basic_auth"] = ("elastic", password)

        # TODO: review config needed, check on startup
        self._client = Elasticsearch(
            config["ckan.search.elasticsearch.url"], **es_config
        )

        return self._client
