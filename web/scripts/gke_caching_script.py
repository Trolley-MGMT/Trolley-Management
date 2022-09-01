import logging
import os
import platform
import json

from dataclasses import asdict
import getpass as gt
from subprocess import PIPE, run

from web.mongo_handler.mongo_utils import insert_cache_object
from web.mongo_handler.mongo_objects import GKECacheObject

from google.cloud.compute import ZonesClient
from google.oauth2 import service_account
from googleapiclient import discovery

from web.variables.variables import GKE

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.FileHandler('Caching.log')
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

LOCAL_USER = gt.getuser()

if 'Darwin' in platform.system():
    CREDENTIALS_PATH = '/Users/pavelzagalsky/Documents/trolley/creds.json'
else:
    CREDENTIALS_PATH = '/tmp/google_credentials'


PROJECT_NAME = os.environ['PROJECT_NAME']

credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_PATH)
service = discovery.build('container', 'v1', credentials=credentials)


def fetch_zones() -> list:
    logger.info(f'A request to fetch zones has arrived')
    compute_zones_client = ZonesClient(credentials=credentials)
    zones_object = compute_zones_client.list(project=PROJECT_NAME)
    zones_list = []
    for zone in zones_object:
        zones_list.append(zone.name)
    return zones_list


def fetch_regions() -> list:
    logger.info(f'A request to fetch regions has arrived')
    compute_zones_client = ZonesClient(credentials=credentials)
    zones_object = compute_zones_client.list(project=PROJECT_NAME)
    regions_list = []
    for zone_object in zones_object:
        zone_object_url = zone_object.region
        region_name = zone_object_url.split('/')[-1]
        if region_name not in regions_list:
            regions_list.append(region_name)
    return regions_list


def fetch_versions(zones_list):
    for zone in zones_list:
        name = f'projects/{PROJECT_NAME}/locations/{zone}'
        request = service.projects().locations().getServerConfig(name=name)
        response = request.execute()
        available_gke_versions = []
        for stable_gke_version in response['channels'][2]['validVersions']:
            available_gke_versions.append(stable_gke_version)
        return available_gke_versions


def fetch_gke_image_types(zones_list):
    for zone in zones_list:
        name = f'projects/{PROJECT_NAME}/locations/{zone}'
        request = service.projects().locations().getServerConfig(name=name)
        response = request.execute()
        available_images = []
        for image in response['validImageTypes']:
            if 'WINDOWS' not in image and image != 'COS':  # There's a technical issue at the moment supporting
                # Windows based nodes
                available_images.append(image)
        return available_images


def create_regions_and_zones_dict(regions_list, zones_list):
    zones_regions_dict = {}
    for region in regions_list:
        for zone in zones_list:
            if region in zone:
                if region not in zones_regions_dict.keys():
                    zones_regions_dict[region] = [zone]
                else:
                    zones_regions_dict[region].append(zone)
    return zones_regions_dict


def main():
    zones_list = fetch_zones()
    regions_list = fetch_regions()
    gke_image_types = fetch_gke_image_types(zones_list=zones_list)
    versions_list = fetch_versions(zones_list=zones_list)
    zones_regions_dict = create_regions_and_zones_dict(regions_list=regions_list, zones_list=zones_list)

    gke_caching_object = GKECacheObject(
        zones_list=zones_list,
        versions_list=versions_list,
        regions_list=regions_list,
        gke_image_types=gke_image_types,
        regions_zones_dict=zones_regions_dict)
    insert_cache_object(caching_object=asdict(gke_caching_object), provider=GKE)


if __name__ == '__main__':
    main()
