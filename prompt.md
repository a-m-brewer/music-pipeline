# Overview

I have a music organization pipeline in @tag_and_move.py which you should only use as reference of the workflow. I want to build an AI powered music organization pipeline.

Currenly with the tag and move script I am doing this all by hand, I would like to speed the process up with AI.

# Current Workflow

1. The script goes through the source directory and finds the first item
2. A box appears with the current tags and I review the state they're currently in
3. If its ok as is move it to the destination where the script has a specific naming style based on the tags
4. If I recognise it I can instantly write the tags
5. Otherwise, (most of the time) if there are bad tags, often with no tags at all and the title being the only thing to go off
   1. I search the internet the name of the file / artist and title
      1. Spotify
      2. Soundcloud
      3. anywhere a google search shows the results for
   2. A lot of my music is not mainstream and old electronic music that was only ever on spotify
      1. This is why the standard approach of a music database like MusicBrainz never work because these are not label released songs from itunes etc
         1. These tools can help but not as much as a normal library
6. There is also a dicard directory as sometimes the song can't be identified at all or I don't want it in the new library (a dj mix rather than song)
7. The goal is to eventually make the source empty and have all my music organized

# Library
- Source: /Volumes/Media/Music Old
- Destination: /Volumes/Media/yams/media/music
- Discard: /Volumes/Media/Music Discard

# Goal
- I want the AI assistance mostly around step 5.
- I need to incorporate all the tools possible, music tags, internet search etc. And anything else you think will help
- Ideally this tool will have the AI do most of the identification with a confidence threshold, (or some other metric) where only then a human intervenes
- This tool can not rely on music tag databases, has to include internet searches.

# Question

- Ask any follow ups and explore the tag_and_move.py script fully