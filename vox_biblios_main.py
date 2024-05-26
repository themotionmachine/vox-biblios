#!/opt/anaconda3/envs/prime/bin/python

import pandas as pd
import os
import requests
import re
import random
import xmltodict
import ast
import nltk
from podgen import Podcast, Episode, Media
from time import sleep
import logging
import boto3
from botocore.exceptions import ClientError
import sys
from datetime import datetime, timezone




def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def update_rss(update_payload):

        oldrss = grab_old_rss_file()
        df = parse_old_rss_file(oldrss)
        p = create_podcast()
        if isinstance(df,str) ==True:
            eplist = []
        else:
            eplist = [create_episode(x, df) for x in df.index]
        p.episodes += eplist
        for y in update_payload: #LEFT OFF HERE
            newep = Episode(title= str(y[1]), media=Media(y[0]), summary=y[1], publication_date= datetime.now(timezone.utc))
            print(str(y[1]))
            p.episodes.append(newep)
            print('ididit', newep)  
        p.rss_file('/Users/rwm/Desktop/Voxbiblios/voxbiblios.rss')


def send_polly_job(text):
    polly_client = boto3.Session(
                aws_access_key_id='AKIAU27ONBILE72PPU7E',                  
    aws_secret_access_key='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',
    region_name='us-east-1').client('polly')
    


    response = polly_client.start_speech_synthesis_task(VoiceId='Joanna',
                OutputS3BucketName='vox-biblios',
                OutputS3KeyPrefix='key',
                OutputFormat='mp3', 
                Text=text,
                Engine='neural')
    return response


def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_name)

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


# creates episode with the current system date and time

def create_episode(x, df):
    try:

        return Episode(
     title= df.iloc[x]['title'],
     media=Media(df.iloc[x]['url']),
     summary=df.iloc[x]['description'],
    publication_date= df.iloc[x]['pubDate']

   )
    except:
        # return episode with default date value of jan 1 2020
        return Episode(
     title= df.iloc[x]['title'],
     media=Media(df.iloc[x]['url']),
     summary=df.iloc[x]['description'],
    publication_date= '2020-01-01T00:00:00Z'
        )

def create_podcast():
    p = Podcast(
   name="Vox Biblios",
   description="it is the vox biblios",
   website="http://example.org/animals-alphabetically",
   explicit=False,
)
    return p

def grab_old_rss_file():
    response = requests.get('https://vox-biblios.s3.amazonaws.com/voxbiblios.rss')
    return response

def parse_old_rss_file(oldrss):
    xmlDict = xmltodict.parse(oldrss.text)
    try:
        
        df = pd.DataFrame(xmlDict['rss']['channel']['item'])
        df['url'] = df['enclosure'].apply(lambda x: x['@url'])
    except: 
        df = 'df'
    return df



def read_source(source):
    with open(source) as f:
        lines = f.read()
    return lines

def write_text(x, title):
    f = open(title, 'w')
    f.write(x)
    f.close()
    
def remove_urls(x):
    x = re.sub(r'http\S+', '', x)
    x = re.sub(r'www\S+', '', x)
    return x

def remove_noise(y):

    eprint(len(y))
    y = y.replace("   ", '. ')
    y = y.replace("\t", '. ')
    eprint(len(y))
    corpus = y
    sentences = nltk.sent_tokenize(corpus)

    continuer = [s for s in sentences if sentences.count(s) <= 10]
    dupes = [s for s in sentences if sentences.count(s) > 10]
    eprint(dupes)

    return (' ').join(continuer)

def detect_long_texts(x):
    if len(x) > 99000:
        x = split_long_texts(x,[])
        [eprint(len(y)) for y in x]
        return x
    else:
        x = [x]
        return x 
    
def split_long_texts(target, processq):
    
    a = target[:90000]
    b = target[90000:]
    if len(b) > 90000:
        processq.append(a)
        split_long_texts(b, processq)
    else:
        processq.append(a)
        processq.append(b)
    return processq
        
def remove_long_numbers(x):
    print('oldlen before removing long numbers', len(x))
    new = re.sub(r'\d{7,}', '', x)
    print('len after removing long numbers', len(new))
    return new


def read_texts_from_folder(folder):
    files = os.listdir(folder)
    dict_of_texts = {}
    for f in files:
        if f.endswith('.txt'):
            with open(folder+'/'+f) as f:
                text = f.read()
                list_of_split_texts = detect_long_texts(text)
                list_of_split_texts = [remove_urls(x) for x in list_of_split_texts]
                list_of_split_texts = [remove_noise(x) for x in list_of_split_texts]
                list_of_split_texts = [remove_long_numbers(x) for x in list_of_split_texts]
                dict_of_texts[f.name.split('/')[-1]] = list_of_split_texts
    return dict_of_texts


# function that runs after rss is updated and uploaded that deletes the texts from the folder
def delete_texts_from_folder(folder):
    files = os.listdir(folder)
    for f in files:
        if f.endswith('.txt'):
            os.remove(folder+'/'+f)
    return True




def delete_old_texts(folder):
    files = os.listdir(folder)
    for f in files:
        eprint(f)
        if f.endswith('.txt'):
            os.remove(folder+'/'+f)


def main():
    dict_of_texts = read_texts_from_folder('/Users/rwm/Desktop/Voxbiblios/')
    update_payload = []
    for k,v in dict_of_texts.items():
        part_counter = 0
        for x in v:
            title = k + '_' + str(part_counter)
            resp = send_polly_job(x)
            sleep(2)
            update_payload.append((resp['SynthesisTask']['OutputUri'], title))
            part_counter += 1
    update_rss(update_payload)
    upload_file('/Users/rwm/Desktop/Voxbiblios/voxbiblios.rss', 'vox-biblios')
    eprint("got here")
    delete_old_texts('/Users/rwm/Desktop/Voxbiblios/')
        

if __name__ == "__main__":
    main()   


 
