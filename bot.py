import praw
import requests
import schedule
import time
import os
import json
import argparse
from datetime import datetime, timedelta, timezone
import ffmpeg  # For merging video and audio
import xml.etree.ElementTree as ET  # For parsing DASH manifest

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Reddit to Facebook Bot")
parser.add_argument("--no-videos", action="store_true", help="Disable video posting")
parser.add_argument("--no-images", action="store_true", help="Disable image posting (including galleries)")
parser.add_argument("--no-greeting", action="store_true", help="Disable the initial greeting message")
parser.add_argument("--no-debug", action="store_true", help="Disable debug logging")
args = parser.parse_args()

# Reddit setup with your credentials
reddit = praw.Reddit(
    client_id="your-reddit-clint-id",
    client_secret="your-reddit-key",
    user_agent="FBRedditBot by u/your-reddit-username",
    username="reddit user name",
    password="your reddit password"
)

# Test Reddit API connection
try:
    subreddit = reddit.subreddit("anime")
    for submission in subreddit.hot(limit=1):
        print(f"Successfully fetched post: {submission.title}")
    print("Reddit API connection is working!")
except Exception as e:
    print(f"Reddit API connection failed: {str(e)}")
    exit(1)

# Facebook setup
PAGE_ACCESS_TOKEN = "FB access token"  # Replace with your token
PAGE_ID = "FB tagrget page ID"  # Replace with your Page ID

# File to store posted Reddit post IDs to avoid duplicates
POSTED_IDS_FILE = "posted_ids.json"

# Maximum file size (20MB in bytes)
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB in bytes (fb api allows 100MB uploads)

# Counter for posts in a batch
POSTS_PER_BATCH = 20   #per batch posting limits
COOLDOWN_SECONDS = 600  # 10 minutes cool down
DELAY_BETWEEN_POSTS = 90  # 90 seconds do not lower than 60
posts_in_batch = 0
download_failures = 0
MAX_FAILURES_BEFORE_NOTIFICATION = 5

# List of subreddits to fetch posts from (deduplicated)
SUBREDDITS = [
    "anime",
]

# Function to determine the time-based greeting
def get_time_based_greeting():
    current_hour = datetime.now(timezone.utc).hour
    if 5 <= current_hour < 12:
        return "Good morning"
    elif 12 <= current_hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"

# Post a text message to Facebook
def post_text_to_facebook(message):
    url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/feed"
    payload = {
        "message": message,
        "access_token": PAGE_ACCESS_TOKEN
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        print("Text message posted successfully!")
    else:
        print(f"Error posting text message: {response.text}")

# Post multiple images to Facebook in a single post
def post_multiple_images_to_facebook(caption, image_paths):
    photo_ids = []
    for image_path in image_paths:
        url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/photos"
        files = {"source": open(image_path, "rb")}
        payload = {
            "published": "false",  # Upload as unpublished
            "access_token": PAGE_ACCESS_TOKEN
        }
        response = requests.post(url, files=files, data=payload)
        files["source"].close()
        if response.status_code == 200:
            photo_id = response.json().get("id")
            photo_ids.append(photo_id)
            print(f"Uploaded image {image_path} with ID {photo_id}")
        else:
            print(f"Error uploading image {image_path}: {response.text}")
            return False

    url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/feed"
    payload = {
        "message": caption,
        "access_token": PAGE_ACCESS_TOKEN
    }
    for i, photo_id in enumerate(photo_ids):
        payload[f"attached_media[{i}]"] = f'{{"media_fbid":"{photo_id}"}}'
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        print("Multiple images posted successfully!")
        return True
    else:
        print(f"Error posting multiple images: {response.text}")
        return False

# Load previously posted IDs
def load_posted_ids():
    if os.path.exists(POSTED_IDS_FILE):
        with open(POSTED_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()

# Save posted IDs
def save_posted_id(post_id):
    posted_ids = load_posted_ids()
    posted_ids.add(post_id)
    with open(POSTED_IDS_FILE, "w") as f:
        json.dump(list(posted_ids), f)

# Check if the file size is under 20MB
def check_file_size(url):
    try:
        headers = {"User-Agent": "FBRedditBot/1.0 (by /u/Deablo_Demon_Lord)"}
        response = requests.head(url, headers=headers, allow_redirects=True)
        size = int(response.headers.get("content-length", 0))
        return size <= MAX_FILE_SIZE
    except:
        return False

# Download media with retry and delay
def download_media(url, filename, max_retries=3, initial_delay=5):
    for attempt in range(max_retries):
        try:
            headers = {"User-Agent": "FBRedditBot/1.0 (by /u/Deablo_Demon_Lord)"}
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"Successfully downloaded {url} to {filename}")
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                delay = initial_delay * (2 ** attempt)
                print(f"Rate limit hit for {url}. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                print(f"Download failed for {url}: {str(e)}")
                return False
        except Exception as e:
            print(f"Download failed for {url}: {str(e)}")
            return False
    print(f"Failed to download {url} after {max_retries} attempts due to rate limiting.")
    return False

# Extract audio URL from DASH manifest
def get_audio_url_from_dash(dash_url):
    try:
        headers = {"User-Agent": "FBRedditBot/1.0 (by /u/Deablo_Demon_Lord)"}
        response = requests.get(dash_url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to fetch DASH manifest: {dash_url}")
            return None

        root = ET.fromstring(response.content)
        namespaces = {"ns": "urn:mpeg:dash:schema:mpd:2011"}

        for adaptation_set in root.findall(".//ns:AdaptationSet", namespaces):
            content_type = adaptation_set.get("contentType")
            if content_type == "audio":
                representation = adaptation_set.find(".//ns:Representation", namespaces)
                base_url = adaptation_set.find(".//ns:BaseURL", namespaces)
                if base_url is not None:
                    audio_url = base_url.text
                    if not audio_url.startswith("http"):
                        base_path = dash_url.rsplit("/", 1)[0]
                        audio_url = f"{base_path}/{audio_url}"
                    return audio_url

        print(f"No audio stream found in DASH manifest: {dash_url}")
        return None
    except Exception as e:
        print(f"Error parsing DASH manifest {dash_url}: {str(e)}")
        return None

# Merge video and audio using ffmpeg
def merge_video_audio(video_url, audio_url, output_filename):
    try:
        video_file = "temp_video.mp4"
        audio_file = "temp_audio.mp4"
        if not download_media(video_url, video_file):
            print(f"Failed to download video: {video_url}")
            return None
        if not download_media(audio_url, audio_file):
            print(f"Failed to download audio: {audio_url}")
            return None

        video_stream = ffmpeg.input(video_file)
        audio_stream = ffmpeg.input(audio_file)
        output = ffmpeg.output(video_stream, audio_stream, output_filename, vcodec="copy", acodec="aac", strict="experimental")
        ffmpeg.run(output)

        if os.path.exists(video_file):
            os.remove(video_file)
        if os.path.exists(audio_file):
            os.remove(audio_file)

        return output_filename
    except Exception as e:
        print(f"Error merging video and audio: {str(e)}")
        return None

# Post image to Facebook
def post_image_to_facebook(caption, image_path):
    url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/photos"
    files = {"source": open(image_path, "rb")}
    payload = {
        "message": caption,
        "access_token": PAGE_ACCESS_TOKEN
    }
    response = requests.post(url, files=files, data=payload)
    files["source"].close()
    if response.status_code == 200:
        print("Image posted successfully!")
        return True
    else:
        print(f"Error posting image: {response.text}")
        return False

# Post video to Facebook
def post_video_to_facebook(caption, video_path):
    url = f"https://graph-video.facebook.com/v22.0/{PAGE_ID}/videos"
    files = {"source": open(video_path, "rb")}
    payload = {
        "description": caption,
        "access_token": PAGE_ACCESS_TOKEN
    }
    response = requests.post(url, files=files, data=payload)
    files["source"].close()
    if response.status_code == 200:
        print("Video posted successfully!")
        return True
    else:
        print(f"Error posting video: {response.text}")
        return False

# Countdown timer for the delay between posts
def countdown(seconds):
    for i in range(seconds, 0, -1):
        print(f"Waiting {i} seconds...", end="\r")
        time.sleep(1)
    print(" " * 50, end="\r")  # Clear the line after countdown

# Main job to fetch and post media
def job():
    global posts_in_batch, download_failures
    posted_ids = load_posted_ids()
    subreddit_string = "+".join(SUBREDDITS)
    subreddit = reddit.subreddit(subreddit_string)

    twelve_hours_ago = datetime.now(timezone.utc) - timedelta(hours=12)
    twelve_hours_ago_timestamp = int(twelve_hours_ago.timestamp())
    if not args.no_debug:
        print(f"Current UTC time: {datetime.now(timezone.utc)}")
        print(f"12 hours ago (UTC): {twelve_hours_ago}")
        print(f"Fetching posts from {subreddit_string}...")

    eligible_posts_found = 0
    try:
        for submission in subreddit.new(limit=200):
            if not args.no_debug:
                print(f"Checking post {submission.id}: {submission.title}")
                print(f"Post creation time (UTC): {datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)}")
            if submission.id in posted_ids:
                if not args.no_debug:
                    print(f"Post {submission.id} already posted, skipping")
                continue

            if submission.created_utc < twelve_hours_ago_timestamp:
                if not args.no_debug:
                    print(f"Post {submission.id} is older than 12 hours, skipping")
                continue

            media_url = None
            is_video = False
            audio_url = None
            if not args.no_images and submission.url.endswith((".jpg", ".jpeg", ".png", ".gif")):
                media_url = submission.url
            elif not args.no_videos and hasattr(submission, "media") and submission.media:
                if "reddit_video" in submission.media:
                    media_url = submission.media["reddit_video"]["fallback_url"]
                    is_video = True
                    if "dash_url" in submission.media["reddit_video"]:
                        dash_url = submission.media["reddit_video"]["dash_url"]
                        audio_url = get_audio_url_from_dash(dash_url)

            if not media_url:
                if not args.no_debug:
                    print(f"Post {submission.id} has no media, skipping")
                continue

            if not check_file_size(media_url):
                if not args.no_debug:
                    print(f"Media too large for post {submission.id}: {submission.url}")
                continue

            eligible_posts_found += 1
            if not args.no_debug:
                print(f"Eligible post found: {submission.id} (Total eligible: {eligible_posts_found})")

            if is_video and not args.no_videos:
                if audio_url and check_file_size(audio_url):
                    output_filename = "temp_media_with_audio.mp4"
                    merged_file = merge_video_audio(media_url, audio_url, output_filename)
                    if merged_file and os.path.exists(merged_file):
                        caption = submission.title
                        success = post_video_to_facebook(caption, merged_file)
                        if os.path.exists(merged_file):
                            os.remove(merged_file)
                    else:
                        print(f"Failed to merge audio for video post {submission.id}, posting without audio")
                        filename = "temp_media.mp4"
                        if download_media(media_url, filename):
                            caption = submission.title
                            success = post_video_to_facebook(caption, filename)
                            if os.path.exists(filename):
                                os.remove(filename)
                        else:
                            print(f"Failed to download video for post {submission.id}")
                            download_failures += 1
                            if download_failures >= MAX_FAILURES_BEFORE_NOTIFICATION:
                                post_text_to_facebook("Warning: Bot is encountering repeated download failures due to rate limiting. Please check the logs.")
                                download_failures = 0
                            continue
                else:
                    print(f"No audio available for video post {submission.id}, posting without audio")
                    filename = "temp_media.mp4"
                    if download_media(media_url, filename):
                        caption = submission.title
                        success = post_video_to_facebook(caption, filename)
                        if os.path.exists(filename):
                            os.remove(filename)
                    else:
                        print(f"Failed to download video for post {submission.id}")
                        download_failures += 1
                        if download_failures >= MAX_FAILURES_BEFORE_NOTIFICATION:
                            post_text_to_facebook("Warning: Bot is encountering repeated download failures due to rate limiting. Please check the logs.")
                            download_failures = 0
                        continue
            elif not args.no_images and hasattr(submission, "is_gallery") and submission.is_gallery:
                media_urls = []
                image_paths = []
                try:
                    gallery_items = submission.gallery_data["items"][:10]
                    for item in gallery_items:
                        media_id = item["media_id"]
                        media_metadata = submission.media_metadata[media_id]
                        if media_metadata["status"] == "valid" and media_metadata["e"] == "Image":
                            media_url = media_metadata["s"]["u"]
                            if check_file_size(media_url):
                                media_urls.append(media_url)
                            else:
                                if not args.no_debug:
                                    print(f"Gallery image too large: {media_url}")
                                continue

                    for i, media_url in enumerate(media_urls):
                        filename = f"temp_media_{i}.jpg"
                        if download_media(media_url, filename):
                            image_paths.append(filename)
                        else:
                            print(f"Failed to download gallery image: {media_url}")
                            download_failures += 1
                            if download_failures >= MAX_FAILURES_BEFORE_NOTIFICATION:
                                post_text_to_facebook("Warning: Bot is encountering repeated download failures due to rate limiting. Please check the logs.")
                                download_failures = 0

                    if image_paths:
                        caption = submission.title
                        success = post_multiple_images_to_facebook(caption, image_paths)
                    else:
                        if not args.no_debug:
                            print(f"No valid images in gallery for post {submission.id}")
                        continue

                    for image_path in image_paths:
                        if os.path.exists(image_path):
                            os.remove(image_path)
                except Exception as e:
                    print(f"Error processing gallery post {submission.id}: {str(e)}")
                    continue
            elif not args.no_images:
                filename = "temp_media.jpg"
                if not download_media(media_url, filename):
                    print(f"Failed to download image for post {submission.id}")
                    download_failures += 1
                    if download_failures >= MAX_FAILURES_BEFORE_NOTIFICATION:
                        post_text_to_facebook("Warning: Bot is encountering repeated download failures due to rate limiting. Please check the logs.")
                        download_failures = 0
                    continue
                caption = submission.title
                success = post_image_to_facebook(caption, filename)
                if os.path.exists(filename):
                    os.remove(filename)
            else:
                if not args.no_debug:
                    print(f"Skipping post {submission.id} due to disabled image/video modules")
                continue

            if success:
                save_posted_id(submission.id)
                posts_in_batch += 1
                print(f"Posted {posts_in_batch}/{POSTS_PER_BATCH} posts in this batch")
                countdown(DELAY_BETWEEN_POSTS)
                if posts_in_batch >= POSTS_PER_BATCH:
                    print(f"Reached {POSTS_PER_BATCH} posts. Cooling down for {COOLDOWN_SECONDS} seconds...")
                    time.sleep(COOLDOWN_SECONDS)
                    posts_in_batch = 0
                    print("Cooldown finished. Resuming posting...")
            else:
                print(f"Failed to post {submission.id}, continuing to next post")
                continue

        if not args.no_debug:
            print(f"Finished processing posts. Eligible posts found: {eligible_posts_found}")
            if eligible_posts_found == 0:
                print("No eligible posts found in this batch. Waiting for next scheduled run...")
    except Exception as e:
        print(f"Error fetching Reddit posts: {str(e)}")

# Initial setup when the bot starts
print("The bot has started")
if not args.no_greeting:
    greeting = get_time_based_greeting()
    post_text_to_facebook(f"{greeting}, the bot has started!")

# Run the job immediately on start
job()

# Schedule to run every 1 minute
schedule.every(1).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(60)
