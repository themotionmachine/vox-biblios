from podgen import Podcast, Episode, Media
import pandas as pd
import xmltodict
from logging_utils import logger

def create_podcast():
    logger.info("Creating new podcast object")
    podcast = Podcast(
        name="Vox Biblios",
        description="I speak with the voices of all the words I've seen.",
        website="disinfo-policy.org",
        explicit=False,
    )
    podcast.image = "https://s3.us-east-1.amazonaws.com/vox-biblios/a91a07d7-f634-4fa6-ae03-c2ff1764a07b_ryan__dont_not_return_without_me_lattice_of_shadow_summer_morning_paint_the_concept_in_the_shimmering_air.png"
    return podcast

def create_episode(df, index):
    try:
        logger.debug(f"Creating episode for index: {index}")
        episode = Episode(
            title=df.iloc[index]['title'],
            media=Media(df.iloc[index]['url']),
            summary=df.iloc[index]['description'],
            publication_date=df.iloc[index]['pubDate']
        )
        logger.debug(f"Episode created successfully: {episode.title}")
        return episode
    except Exception as e:
        logger.error(f"Error creating episode for index {index}: {str(e)}", exc_info=True)
        return None

def parse_old_rss_file(oldrss):
    try:
        logger.info("Parsing old RSS file")
        xmlDict = xmltodict.parse(oldrss.text)
        df = pd.DataFrame(xmlDict['rss']['channel']['item'])
        df['url'] = df['enclosure'].apply(lambda x: x['@url'])
        logger.info(f"Parsed {len(df)} items from old RSS file")
        return df
    except Exception as e:
        logger.error(f"Error parsing old RSS file: {str(e)}", exc_info=True)
        return 'df'