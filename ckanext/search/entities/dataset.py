import json
from typing import Any, Iterable, Optional

import ckan.authz as authz
from ckan import model
from ckan.lib.navl.dictization_functions import MissingNullEncoder
from ckan.lib.plugins import get_permission_labels
from ckan.plugins import SingletonPlugin
from ckan.plugins.toolkit import NotFound, config, get_action, get_validator
from ckan.types import ActionResult, Context, Schema

from ckanext.search.filters import FilterOp
from ckanext.search.schema import (DEFAULT_DATASET_SEARCH_SCHEMA, SearchSchema,
                                   get_search_schema)


class DatasetSearchEntity(SingletonPlugin):

    def entity_type(self) -> str:
        """Return a string id for the entity that this plugin handles
        (e.g. 'dataset', 'organization', 'report', etc)"""

        return "dataset"

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
        return DEFAULT_DATASET_SEARCH_SCHEMA

    def search_query_schema(self) -> Schema:
        """
        Return a schema to validate custom query parameters. Can be used to add new
        supported query parameters.

        For datasets, these are:

        * include_drafts: if ``True``, draft datasets will be included in the
            results. A user will only be returned their own draft datasets, and a
            sysadmin will be returned all draft datasets. Optional, the default is
            ``False``.
        * include_deleted: if ``True``, deleted datasets will be included in the
            results (site configuration "ckan.search.remove_deleted_packages" must
            be set to False). Optional, the default is ``False``.
        * include_private: if ``True``, private datasets will be included in
            the results. Only private datasets from the user's organizations will
            be returned and sysadmins will be returned all private datasets.
            Optional, the default is ``False``.
        """
        search_query_schema = {}

        ignore_missing = get_validator("ignore_missing")
        ignore_empty = get_validator("ignore_empty")
        boolean_validator = get_validator("boolean_validator")

        search_query_schema["include_drafts"] = [
            ignore_missing,
            ignore_empty,
            boolean_validator,
        ]
        search_query_schema["include_deleted"] = [
            ignore_missing,
            ignore_empty,
            boolean_validator,
        ]
        search_query_schema["include_private"] = [
            ignore_missing,
            ignore_empty,
            boolean_validator,
        ]

        return search_query_schema

    def _get_user_permission_labels(self, context: Context) -> list[str] | None:

        user = context.get("user")
        if context.get("ignore_auth") or (user and authz.is_sysadmin(user)):
            labels = None
        else:
            labels = get_permission_labels().get_user_dataset_labels(
                context["auth_user_obj"]
            )

        return labels

    def _add_filter_to_query(
        self, query_params: dict[str, Any], filter_op: FilterOp
    ) -> dict[str, Any]:

        if existing_filter_op := query_params["filters"]:
            if existing_filter_op.op == "$and":
                # Add the filter to the existing AND filters
                existing_filter_op.value.append(filter_op)
            else:
                # Wrap existing filters and the new one in an AND operation
                query_params["filters"] = FilterOp(
                    field=None, op="$and", value=[existing_filter_op, filter_op]
                )
            pass
        else:
            # If no filters already defined, just use the new filter
            query_params["filters"] = filter_op

        return query_params

    def before_query(
        self, query_params: dict[str, Any], context: Context
    ) -> dict[str, Any]:
        """
        Called before sending the query to the search provider, allows to modify
        the sent query parameters.
        """

        include_drafts = query_params.get("additional_params", {}).pop(
            "include_drafts", False
        )
        include_deleted = query_params.get("additional_params", {}).pop(
            "include_deleted", False
        )
        include_private = query_params.get("additional_params", {}).pop(
            "include_private", False
        )

        if not include_private:
            private_filter = FilterOp(field="private", op="eq", value=False)
            self._add_filter_to_query(query_params, private_filter)

        # TODO: Check if state is previously defined in filters
        # https://github.com/ckan/ckan/blob/89107b266508a830e903d2765670827380f1e5ae/ckan/logic/action/get.py#L1841
        states = ["active"]
        if include_drafts:
            states.append("draft")
        if include_deleted:
            states.append("deleted")
        states_filter = FilterOp(field="state", op="in", value=states)
        self._add_filter_to_query(query_params, states_filter)

        # Permission labels
        if labels := self._get_user_permission_labels(context):
            perm_labels_filter_op = FilterOp(
                field="permission_labels", op="in", value=labels
            )
            self._add_filter_to_query(query_params, perm_labels_filter_op)

        return query_params

    def after_query(
        self, query_results: dict[str, Any], query_params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Called just before returning the search results. Besides the results from
        the provider, it also receives the params used in the query.
        """

        return query_results

    def _get_dataset_ids(self, ids: Optional[Iterable[str]] = []) -> Iterable[str]:

        q = model.Session.query(model.Package.id)
        if ids:
            q = q.filter(model.Package.id.in_(ids))

        # TODO: review this
        if config.get("ckan.search.remove_deleted_packages"):
            package_ids = q.filter(model.Package.state != "deleted")

        package_ids = [r[0] for r in q.all()]

        if ids and len(package_ids) != len(list(ids)):
            missing_ids = {id_ for id_ in package_ids} - set(ids)
            raise NotFound(f"Dataset with id(s) not found: {missing_ids}")

        return package_ids

    def _get_dataset_dict(self, id_: str) -> ActionResult.PackageShow:
        context = {
            "ignore_auth": True,
            "use_cache": False,
            # "for_indexing": True,  # TODO: implement support in core?
        }

        # Request the validated dataset
        dataset_dict = get_action("package_show")(context, {"id": id_})

        return dataset_dict

    def _transform_search_data(
        self, dataset_dict: ActionResult.PackageShow
    ) -> dict[str, Any]:

        # TODO: make this a public interface method? i.e is it useful elsewhere?

        search_data = {}

        # TODO: choose what to index here?
        # For now let's remove everything not explicitly added to the search schema
        schema = get_search_schema("dataset")
        for key, value in dataset_dict.items():

            # TODO: handle organization, resource fields, etc
            if key in schema.get("fields", []):
                search_data[key] = value

        search_data["tags"] = [t["name"] for t in search_data.get("tags", [])]

        # Add search-specific fields

        search_data["entity_type"] = "dataset"

        search_data["validated_data_dict"] = json.dumps(
            search_data, cls=MissingNullEncoder
        )

        # permission labels determine visibility in search, can't be set
        # in original dataset or before_dataset_index plugins
        id_ = dataset_dict["id"]
        search_data["permission_labels"] = get_permission_labels().get_dataset_labels(
            model.Package.get(id_)
        )

        return search_data

    def existing_record_ids(self, entity_type: str) -> Iterable[str]:
        """return a list or iterable of all record ids for the given entity type
        managed by this feature.
        This method is used to identify missing and orphan records in the
        search index"""

        # TODO: do we really need entity_type?
        assert entity_type == "dataset"

        return self._get_dataset_ids()

    def fetch_records(
        self, entity_type: str, ids: Optional[Iterable[str]] = []
    ) -> Iterable[dict[str, Any]]:
        """generator of all records for this entity type managed by this
        feature, or only records for the ids passed if not None.
        This method is used to rebuild all or some records in the search
        index"""

        # TODO: do we really need entity_type?
        assert entity_type == "dataset"

        for id_ in self._get_dataset_ids(ids):
            dataset_dict = self._get_dataset_dict(id_)
            yield self._transform_search_data(dataset_dict)
