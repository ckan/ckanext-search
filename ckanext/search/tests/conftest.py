from unittest import mock

import pytest


from ckanext.search.interfaces import ISearchFeature, ISearchProvider
from ckanext.search.index import clear_index


@pytest.fixture
def clean_search_index():
    clear_index()
    yield
    clear_index()


class MockSearchFeature:

    def before_query(self, query_dict, context):
        pass

    def after_query(self, query_results, query_dict):
        pass

    def search_query_schema(self):
        return {
            "custom_param": [],
        }


class MockSearchProvider:

    id = "test-provider"

    def search_query_schema(self):
        return {
            "qf": [],
            "df": [],
        }

    search_query = mock.MagicMock()


@pytest.fixture
def mock_search_plugins():
    """Fixture that mocks plugin implementations for search tests."""
    mock_provider = MockSearchProvider()
    mock_feature = MockSearchFeature()

    with mock.patch(
        "ckanext.search.logic.actions.PluginImplementations"
    ) as mock_plugin_implementations:

        def choose(interface):
            if interface == ISearchProvider:
                return [mock_provider]
            elif interface == ISearchFeature:
                return [mock_feature]
            return []

        mock_plugin_implementations.side_effect = choose

        # Return the mocks so tests can access them for assertions
        yield {
            "provider": mock_provider,
            "feature": mock_feature,
        }
