import json
from typing import Any, Iterable, Optional

import ckan.authz as authz
from ckan import model
from ckan.lib.navl.dictization_functions import MissingNullEncoder
from ckan.lib.plugins import get_permission_labels
from ckan.plugins import SingletonPlugin
from ckan.plugins.toolkit import NotFound, config, get_action, get_validator
from ckan.types import ActionResult, Context, Schema
from sqlalchemy.sql.expression import true

from ckanext.search.filters import FilterOp
from ckanext.search.schema import (DEFAULT_ORGANIZATION_SEARCH_SCHEMA,
                                   SearchSchema, get_search_schema)


class OrganizationSearchEntity(SingletonPlugin):

    def entity_type(self) -> str:
        """Return a string id for the entity that this plugin handles
        (e.g. 'dataset', 'organization', 'report', etc)"""

        return "organization"

    def search_schema(self) -> SearchSchema:
        """Return a full search schema for this particular entity type.

        TODO: link to docs with a proper spec
        Search schemas are defined as dicts with the following format:

            {
                "version": 1,
                "fields": {
                    <field_name>: {
                        "type": <type>,
                        "multiple": True/False,
                        "indexed": True/False,
                        "stored": True/False,
                        ...
                    },
                    ...

                    }
                }

            }

        """
        return DEFAULT_ORGANIZATION_SEARCH_SCHEMA

    def search_query_schema(self) -> Schema:
        """
        Return a schema to validate custom query parameters. Can be used to add new
        supported query parameters.
        """

        return {}

    def before_query(
        self, query_params: dict[str, Any], context: Context
    ) -> dict[str, Any]:
        """
        Called before sending the query to the search provider, allows to modify
        the sent query parameters.
        """

        return query_params

    def after_query(
        self, query_results: dict[str, Any], query_params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Called just before returning the search results. Besides the results from
        the provider, it also receives the params used in the query.
        """

        return query_results

    def _get_org_ids(self, ids: Optional[Iterable[str]] = []) -> Iterable[str]:

        # TODO: more filters (state, type, etc)?
        q = (
            model.Session.query(model.Group.id)
            .filter(model.Group.state != "deleted")
            .filter(model.Group.is_organization == true())
        )
        if ids:
            q = q.filter(model.Group.id.in_(ids))

        org_ids = [r[0] for r in q.all()]

        if ids and len(org_ids) != len(list(ids)):
            missing_ids = {id_ for id_ in org_ids} - set(ids)
            raise NotFound(f"Organization with id(s) not found: {missing_ids}")

        return org_ids

    def _get_org_dict(self, id_: str) -> ActionResult.OrganizationShow:
        context = {
            "ignore_auth": True,
            "use_cache": False,
            # "for_indexing": True,  # TODO: implement support in core?
        }

        # Request the validated dataset
        org_dict = get_action("organization_show")(context, {"id": id_})

        return org_dict

    def _transform_search_data(
        self, org_dict: ActionResult.PackageShow
    ) -> dict[str, Any]:

        # TODO: make this a public interface method? i.e is it useful elsewhere?

        search_data = {}

        # For now let's remove everything not explicitly added to the search schema
        schema = get_search_schema("organization")
        for key, value in org_dict.items():
            # TODO: handle users etc?
            if key in schema.get("fields", []):
                search_data[key] = value

        search_data["entity_type"] = "organization"
        search_data["validated_data_dict"] = json.dumps(
            search_data, cls=MissingNullEncoder
        )

        return search_data

    def existing_record_ids(self, entity_type: str) -> Iterable[str]:
        """return a list or iterable of all record ids for the given entity type
        managed by this feature.
        This method is used to identify missing and orphan records in the
        search index"""

        # TODO: do we really need entity_type?
        assert entity_type == "organization"

        return self._get_org_ids()

    def fetch_records(
        self, entity_type: str, ids: Optional[Iterable[str]] = []
    ) -> Iterable[dict[str, Any]]:
        """generator of all records for this entity type managed by this
        feature, or only records for the ids passed if not None.
        This method is used to rebuild all or some records in the search
        index"""

        # TODO: do we really need entity_type?
        assert entity_type == "organization"

        for id_ in self._get_org_ids(ids):
            org_dict = self._get_org_dict(id_)
            yield self._transform_search_data(org_dict)
