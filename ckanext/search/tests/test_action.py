import pytest

import ckan.plugins as plugins
from ckan.plugins import toolkit
from ckan.tests import helpers

from ckanext.search.filters import FilterOp


pytestmark = [
    pytest.mark.usefixtures("with_plugins"),
    pytest.mark.ckan_config("ckan.search.search_provider", "test-provider"),
]


def test_standard_params(mock_search_plugins):
    helpers.call_action(
        "search",
        entity_type="dataset",
        q="cats",
        limit=10,
        start=10,
        sort=["title asc"],
        filters={"entity_type": "dataset"},
    )

    query_params = mock_search_plugins["provider"].search_query.call_args[1]
    assert query_params["q"] == "cats"
    assert query_params["limit"] == 10
    assert query_params["start"] == 10
    assert query_params["sort"] == ["title asc"]
    assert query_params["filters"] == FilterOp(
        field=None,
        op="$and",
        value=[
            FilterOp(field="entity_type", op="eq", value="dataset"),
            FilterOp(field="private", op="eq", value=False),
            FilterOp(field="state", op="in", value=["active"]),
        ],
    )


def test_standard_params_are_converted(mock_search_plugins):
    helpers.call_action(
        "search",
        entity_type="dataset",
        q="cats",
        limit="10",
        start="10",
        sort='["title asc"]',
        filters='{"entity_type": "dataset"}',
    )

    query_params = mock_search_plugins["provider"].search_query.call_args[1]
    assert query_params["q"] == "cats"
    assert query_params["limit"] == 10
    assert query_params["start"] == 10
    assert query_params["sort"] == ["title asc"]
    assert query_params["filters"] == FilterOp(
        field=None,
        op="$and",
        value=[
            FilterOp(field="entity_type", op="eq", value="dataset"),
            FilterOp(field="private", op="eq", value=False),
            FilterOp(field="state", op="in", value=["active"]),
        ],
    )


def test_standard_params_are_validated(mock_search_plugins):

    with pytest.raises(toolkit.ValidationError) as exc_info:
        helpers.call_action(
            "search",
            entity_type="dataset",
            q="cats",
            limit="a",
            start="b",
            sort='{"title": "asc"}',
            filters="aa",
        )

    assert exc_info.value.error_dict["limit"][0] == "Invalid integer"
    assert exc_info.value.error_dict["start"][0] == "Invalid integer"
    assert (
        exc_info.value.error_dict["filters"][0]
        == "Filters must be defined as a dict or a list of dicts"
    )
    # TODO: use a better validator for lists for sort
    # assert exc_info.value.error_dict["sort"][0] == "Could not parse as valid JSON"


def test_provider_params(mock_search_plugins):
    helpers.call_action(
        "search",
        entity_type="dataset",
        q="cats",
        df="title",
        qf="title^4.0 description^2.0",
    )

    query_params = mock_search_plugins["provider"].search_query.call_args[1]
    assert query_params["q"] == "cats"
    assert query_params["additional_params"]["df"] == "title"
    assert query_params["additional_params"]["qf"] == "title^4.0 description^2.0"


def test_feature_params(mock_search_plugins):
    helpers.call_action(
        "search",
        entity_type="dataset",
        q="cats",
        custom_param="hi",
    )

    query_params = mock_search_plugins["provider"].search_query.call_args[1]
    assert query_params["q"] == "cats"
    assert query_params["additional_params"]["custom_param"] == "hi"


def test_unknown_params_fail(mock_search_plugins):

    with pytest.raises(toolkit.ValidationError) as exc_info:
        helpers.call_action(
            "search",
            entity_type="dataset",
            q="cats",
            not_="a",
            known="b",
        )

    assert exc_info.value.error_dict["message"] == "Unknown parameters: not_, known"
