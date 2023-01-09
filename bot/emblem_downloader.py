import logging
from typing import Optional

import requests

LOG = logging.getLogger(__name__)

# this special header allows us the detect the fallback image, if the guild does not exist or there is not emblem1
EMBLEM_STATUS_HEADER = "Emblem-Status"


def download_guild_emblem(guild_id: str, icon_size: int = 64) -> Optional[bytes]:
    """
    Download a guild emblem from emblem.werdes.net and checks if the response contains a real emblem or a fallback placeholder
    :param guild_id: ID of the guild as returned from the gw2 api
    :param icon_size: Optional, size of the image. Anything over 128 is upscaled.
    :return:Icon image data or null if not found
    """
    icon_url = f"https://emblem.werdes.net/emblem/{guild_id}/{icon_size}"
    LOG.debug("Downloading guild emblem from %s", icon_url)
    response = requests.get(icon_url)

    if response.status_code == 200:
        if EMBLEM_STATUS_HEADER in response.headers:
            if response.headers[EMBLEM_STATUS_HEADER] == "OK":
                icon_image_data = response.content
                if len(icon_image_data) <= 100:  # check that response actually contains some data
                    LOG.warning("Very small Response. Guild probably has no icon or an error occured.")
                else:
                    return icon_image_data
            elif response.headers[EMBLEM_STATUS_HEADER] == "NotFound":
                LOG.info("No emblem found for guild.")
            else:
                LOG.warning("Unknown Emblem Status: %s", response.headers[EMBLEM_STATUS_HEADER])
        else:
            LOG.warning("%s header not found in response. Assuming this is an error.", EMBLEM_STATUS_HEADER)
    else:
        LOG.warning("Icon download failed, HTTP Status code was: %s", response.status_code)

    # if anything failed, return None
    return None
