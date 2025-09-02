import json
import logging
from typing import Any

from geomet import wkt

from ckan.plugins import SingletonPlugin, implements
from ckan.plugins.toolkit import Invalid, get_validator, config
from ckan.types import Schema, Context
from ckanext.search.interfaces import ISearchFeature, SearchSchema

from ckanext.search.providers.solr import SolrSchema


log = logging.getLogger(__name__)


def bbox_validator(value):

    # TODO: use all checks and logic from ckanext-spatial

    if isinstance(value, str):
        value = value.split(",")

    if len(value) != 4:
        raise Invalid(
            "Not enough values in bounding box, must be: minx, miny, maxx, maxy"
        )

    try:
        bbox = {}
        bbox["minx"] = float(value[0])
        bbox["miny"] = float(value[1])
        bbox["maxx"] = float(value[2])
        bbox["maxy"] = float(value[3])
    except ValueError:
        raise Invalid(f"Invalid values in bounding box: {value}")

    return bbox


class SpatialSearch(SingletonPlugin):
    """
    Plugin that adds spatial search capabilities to CKAN search.
    """

    implements(ISearchFeature, inherit=True)

    def entity_types(self):

        return ["dataset"]

    def supported_providers(self):

        return ["solr"]

    def initialize_search_provider(
        self, combined_schema: SearchSchema, clear: bool
    ) -> None:

        # TODO BBox fields

        _admin_client = SolrSchema(config["ckan.search.solr.url"])

        field_type = _admin_client.get_field_type("location_rpt")
        if not field_type:
            # TODO: allow customizing
            field_type = {
                "class": "solr.SpatialRecursivePrefixTreeFieldType",
                "geo": "true",
                "maxDistErr": "0.001",
                "distErrPct": "0.025",
                "distanceUnits": "kilometers",
            }

            _admin_client.add_field_type("location_rpt", **field_type)
            log.info("Added field type 'location_rpt' to schema")

        field = _admin_client.get_field("spatial_geom")
        if field:
            log.info("Field 'spatial_geom' exists and clear not provided, skipping")
        else:

            field = {
                "indexed": True,
                "stored": False,
                "multiValued": True,
            }

            resp = _admin_client.add_field("spatial_geom", "location_rpt", **field)
            if "error" in resp:
                msg = ""
                if "details" in resp["error"]:
                    msg = resp["error"]["details"][0]["errorMessages"]
                elif "msg" in resp["error"]:
                    msg = resp["error"]["msg"][:1000]

                log.warning(f'Error creating field "spatial_geom": {msg}')
            else:
                log.info(
                    f"Added field 'spatial_geom' to index, with type location_rpt and params {field}"
                )

    def search_schema(self) -> SearchSchema:
        """Return spatial search schema fields."""
        return {
            "version": 1,
            "fields": {
                "spatial_geom": {"type": "location_rpt"},
                # TODO: bbox field
                # "spatial_bbox": {"type": "string"},
            },
        }

    def before_index(
        self,
        entity_type: str,
        id_: str,
        search_data: dict[str, str | list[str]],
        search_schema: SearchSchema,
    ) -> None:

        if not entity_type == "dataset":
            return

        # TODO: check in extras?
        geom_text = search_data.get("spatial")
        if not geom_text:
            return

        # TODO: copy validation, bounds checking, WKT formatting etc from
        # ckanext-spatial
        # For now we just use geomet

        try:
            geometry = json.loads(geom_text)
        except (AttributeError, ValueError) as e:
            log.error(
                "Geometry not valid JSON {}, not indexing :: {}".format(
                    e, geom_text[:100]
                )
            )
            return None

        search_data["spatial_geom"] = wkt.dumps(geometry, decimals=6)
        search_data.pop("spatial", None)

    def search_query_schema(self) -> Schema:
        """
        Add spatial query parameters to the search query schema.
        """
        search_query_schema = {}

        ignore_missing = get_validator("ignore_missing")
        ignore_empty = get_validator("ignore_empty")

        # Bounding box coordinates: minx, miny, maxx, maxy
        search_query_schema["bbox"] = [ignore_missing, ignore_empty, bbox_validator]

        return search_query_schema

    def before_query(self, query_params: dict[str, Any], context: Context) -> dict[str, Any]:

        if bbox := query_params["additional_params"].get("bbox"):

            if "fq" not in query_params["additional_params"]:
                query_params["additional_params"]["fq"] = []

            query_params["additional_params"]["fq"].append(
                "{{!field f=spatial_geom}}"
                "Intersects(ENVELOPE({minx}, {maxx}, {maxy}, {miny}))".format(**bbox)
            )
            query_params["additional_params"].pop("bbox")

        return query_params
