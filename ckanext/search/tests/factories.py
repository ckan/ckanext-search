import json

from ckan import model
from ckan.lib.navl.dictization_functions import MissingNullEncoder

from ckan.tests import factories as core_factories

from ckanext.search.index import rebuild_index


class CKANIndexedOnlyFactory(core_factories.CKANFactory):

    @classmethod
    def _api_prepare_args(cls, data_dict):
        """Add any extra details for the action."""
        data_dict = super()._api_prepare_args(data_dict)

        data_dict["context"]["for_indexing"] = True
        data_dict["context"]["validate"] = False
        # Prevent actually storing the entity in the database
        data_dict["context"]["defer_commit"] = True

        return data_dict

    @classmethod
    def _api_postprocess_result(cls, result):
        """Modify result before returning it to the consumer."""

        if cls.entity_type:
            rebuild_index(cls.entity_type, ids=[result["id"]])

        model.Session.rollback()

        return result


class IndexedDataset(core_factories.Dataset, CKANIndexedOnlyFactory):

    entity_type = "dataset"


class IndexedOrganization(core_factories.Organization, CKANIndexedOnlyFactory):

    entity_type = "organization"
